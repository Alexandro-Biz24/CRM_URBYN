"""Import CSV gros volume → produits + arborescence catalogues (colonne Urbyn)."""

from __future__ import annotations

import csv
import io
import random
import re
import string
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import admin_catalog_repo as repo
from app.schemas.admin import (
    CatalogCsvImportMode,
    CatalogCsvImportResult,
    CatalogCsvImportRowError,
)
from app.services.admin import AdminError

# Colonnes fixes (avant / hors attributs dynamiques)
_FIXED_HEADERS = {
    "référence",
    "reference",
    "nom commercial",
    "description",
    "prix référence ht",
    "prix reference ht",
    "unité",
    "unite",
    "urbyn",
    "id produit sellsy",
    "fournisseur",
}

_URBYN_PATH_RE = re.compile(r"\[([^\]]+)\]")


def _norm_header(raw: str) -> str:
    return " ".join(raw.replace("\n", " ").replace("\r", " ").split()).strip().lower()


def _parse_price(raw: str) -> Decimal:
    text = (raw or "").strip()
    if not text:
        return Decimal("0")
    text = text.replace(" ", "").replace("€", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _parse_currency(unit: str) -> str:
    """Unité CSV → currency (3 lettres). Défaut EUR si ce n'est pas un code devise."""
    cleaned = (unit or "").strip().upper()
    if len(cleaned) == 3 and cleaned.isalpha():
        return cleaned
    return "EUR"


def _generate_client_sku(db: Session, company_tva: str) -> str:
    for _ in range(40):
        sku = "".join(random.choices(string.ascii_uppercase, k=8))
        if repo.find_product_by_client_sku(db, company_tva, sku) is None:
            return sku
    raise AdminError("sku_generation_failed", "Impossible de générer un SKU unique.")


def _resolve_owner_company(db: Session, company_tva_intra_com: str | None):
    """
    Société propriétaire de TOUS les produits de l'import.
    Valeur UI prioritaire ; vide → Urbanize (défaut).
    """
    tva = (company_tva_intra_com or "").strip()
    if tva:
        company = repo.get_company(db, tva)
        if company is None:
            raise AdminError("company_not_found", "Société introuvable.")
        return company
    return repo.ensure_urbanize_company(db)


def _parse_urbyn_paths(urbyn: str) -> list[list[str]]:
    paths: list[list[str]] = []
    for match in _URBYN_PATH_RE.findall(urbyn or ""):
        segments = [s.strip() for s in match.split("/") if s.strip()]
        if segments:
            paths.append(segments)
    return paths


def _row_dict(headers: list[str], values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, header in enumerate(headers):
        key = _norm_header(header)
        if not key:
            continue
        out[key] = values[i].strip() if i < len(values) else ""
    return out


def _get(row: dict[str, str], *aliases: str) -> str:
    for alias in aliases:
        if alias in row and row[alias]:
            return row[alias]
    return ""


def _slug_sku_part(raw: str, *, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (raw or "").strip()).strip("-")
    return (cleaned.upper() or "X")[:max_len]


def _paths_key(path_strings: list[str]) -> str:
    """Clé stable des chemins Urbyn d'une ligne (ordre indépendant)."""
    return "|".join(sorted({p for p in path_strings if p}))


def _allocate_skus_by_ref_and_urbyn(
    db: Session,
    owner_tva: str,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[CatalogCsvImportRowError]]:
    """
    Référence unique → SKU = Référence (comportement d'origine).

    Même Référence sur plusieurs lignes → autorisé seulement si aucun chemin
    Urbyn en commun entre ces lignes (ex. Acquisition vs Location).
    Sinon → lignes en erreur.

    Quand paths disjoints : produits distincts, SKU suffixé par la feuille.
    """
    errors: list[CatalogCsvImportRowError] = []
    by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in rows:
        base = (item["sku"] or "").strip()
        item["sku_base"] = base
        item["path_set"] = set(item.get("path_strings") or [])
        by_base[base].append(item)

    rejected: set[int] = set()  # line numbers

    for base, group in by_base.items():
        if not base or len(group) < 2:
            continue
        # Vérifier absence de path commun entre chaque paire de lignes
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                common = a["path_set"] & b["path_set"]
                if not common:
                    continue
                msg = (
                    f"Référence « {base} » en double avec chemin(s) Urbyn en commun "
                    f"({', '.join(sorted(common))}). "
                    f"Soit une seule ligne, soit des paths disjoints."
                )
                for item in (a, b):
                    if item["line"] in rejected:
                        continue
                    rejected.add(item["line"])
                    errors.append(
                        CatalogCsvImportRowError(line=item["line"], message=msg)
                    )

    kept = [item for item in rows if item["line"] not in rejected]

    # Quelles Références (encore présentes) ont plusieurs jeux de paths ?
    by_base_kept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in kept:
        by_base_kept[item["sku_base"]].append(item)

    bases_needing_suffix: set[str] = set()
    for base, group in by_base_kept.items():
        if not base:
            continue
        if len({item["paths_key"] for item in group}) > 1:
            bases_needing_suffix.add(base)

    identity_sku: dict[tuple[str, str], str] = {}
    used: set[str] = set()
    warnings: list[CatalogCsvImportRowError] = []

    for item in kept:
        base = item["sku_base"]
        paths_key = item["paths_key"]
        identity = (base.upper(), paths_key)

        if identity in identity_sku:
            item["sku"] = identity_sku[identity]
            continue

        if not base:
            sku = _generate_client_sku(db, owner_tva)
            while sku.upper() in used:
                sku = _generate_client_sku(db, owner_tva)
        elif base in bases_needing_suffix:
            leaf = item["leaf_labels"][0] if item["leaf_labels"] else "PATH"
            sku = f"{base}-{_slug_sku_part(leaf)}"
            n = 2
            while sku.upper() in used:
                sku = f"{base}-{_slug_sku_part(leaf)}-{n}"
                n += 1
            warnings.append(
                CatalogCsvImportRowError(
                    line=item["line"],
                    message=(
                        f"Référence « {base} » sur plusieurs paths Urbyn disjoints "
                        f"→ SKU « {sku} »."
                    ),
                )
            )
        else:
            sku = base

        used.add(sku.upper())
        identity_sku[identity] = sku
        item["sku"] = sku

    return kept, errors + warnings


def import_catalog_csv(
    db: Session,
    *,
    content: bytes,
    mode: CatalogCsvImportMode,
    company_tva_intra_com: str | None = None,
) -> CatalogCsvImportResult:
    # L'UI prime : une seule société pour tout le fichier
    owner = _resolve_owner_company(db, company_tva_intra_com)
    owner_tva = owner.tva_intra_com

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") >= sample.count(",") else ","

    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        raise AdminError("empty_csv", "Le fichier CSV est vide.")

    headers = rows[0]
    norm_headers = [_norm_header(h) for h in headers]
    if "urbyn" not in norm_headers or "nom commercial" not in norm_headers:
        raise AdminError(
            "invalid_csv_headers",
            "Colonnes obligatoires manquantes : « Nom commercial » et « Urbyn ».",
        )

    urbyn_index = norm_headers.index("urbyn")
    dynamic_headers = [
        headers[i]
        for i, nh in enumerate(norm_headers)
        if i > urbyn_index and nh and nh not in _FIXED_HEADERS
    ]

    # Pass 1 — parser le CSV (chemins Urbyn) sans figer l'arborescence encore
    pending_rows: list[dict[str, Any]] = []
    errors: list[CatalogCsvImportRowError] = []
    root_names: set[str] = set()

    for line_no, raw in enumerate(rows[1:], start=2):
        if not any((c or "").strip() for c in raw):
            continue
        row = _row_dict(headers, raw)
        name = _get(row, "nom commercial")
        if not name:
            errors.append(
                CatalogCsvImportRowError(
                    line=line_no,
                    message="Nom commercial manquant — ligne ignorée.",
                )
            )
            continue

        urbyn = _get(row, "urbyn")
        paths = _parse_urbyn_paths(urbyn)
        if not paths:
            errors.append(
                CatalogCsvImportRowError(
                    line=line_no,
                    message="Colonne Urbyn vide ou invalide (attendu [Racine/…/Feuille]) — ligne ignorée.",
                )
            )
            continue

        for segments in paths:
            if segments:
                root_names.add(segments[0])

        attrs: dict[str, str] = {}
        for header in dynamic_headers:
            key = _norm_header(header)
            display = " ".join(header.replace("\n", " ").split()).strip()
            value = row.get(key, "")
            if display and value:
                attrs[display] = value

        unit_raw = _get(row, "unité", "unite")
        if unit_raw and _parse_currency(unit_raw) == "EUR" and len(unit_raw.strip()) != 3:
            attrs.setdefault("Unité", unit_raw)

        fournisseur = _get(row, "fournisseur")
        if fournisseur:
            attrs.setdefault("Fournisseur (CSV)", fournisseur)

        sellsy_id = _get(row, "id produit sellsy")
        if sellsy_id:
            attrs.setdefault("ID Produit Sellsy", sellsy_id)

        pending_rows.append(
            {
                "line": line_no,
                "name": name,
                "sku": _get(row, "référence", "reference"),
                "sellsy_id": sellsy_id,
                "description": _get(row, "description"),
                "price": _parse_price(_get(row, "prix référence ht", "prix reference ht")),
                "currency": _parse_currency(unit_raw),
                "paths": paths,
                "attrs": attrs,
            }
        )

    # Mode destructif : pour chaque racine du CSV, vider les produits ET
    # détruire tous les catalogues enfants, puis on recreera depuis le fichier.
    catalogs_cleared = 0
    if mode == CatalogCsvImportMode.destructive:
        for root_name in sorted(root_names):
            root = repo._find_root_by_name(db, root_name)
            if root is None:
                continue
            catalogs_cleared += repo.purge_catalog_subtree(db, root.id)

    # Pass 2 — (re)créer l'arborescence et résoudre les feuilles
    path_cache: dict[str, tuple[int, list[str]]] = {}
    created_catalog_ids: set[int] = set()
    parsed_rows: list[dict[str, Any]] = []

    for item in pending_rows:
        leaf_ids: list[int] = []
        leaf_labels: list[str] = []
        path_strings: list[str] = []
        for segments in item["paths"]:
            cache_key = "/".join(segments)
            path_strings.append(cache_key)
            if cache_key in path_cache:
                leaf_id, labels = path_cache[cache_key]
            else:
                leaf, created_ids, _chain = repo.ensure_catalog_path(db, segments)
                leaf_id = leaf.id
                labels = [segments[-1]] if segments else []
                path_cache[cache_key] = (leaf_id, labels)
                created_catalog_ids.update(created_ids)
            leaf_ids.append(leaf_id)
            leaf_labels.extend(labels)

        parsed_rows.append(
            {
                "line": item["line"],
                "name": item["name"],
                "sku": item["sku"],
                "sellsy_id": item["sellsy_id"],
                "description": item["description"],
                "price": item["price"],
                "currency": item["currency"],
                "leaf_ids": list(dict.fromkeys(leaf_ids)),
                "leaf_labels": leaf_labels,
                "path_strings": path_strings,
                "paths_key": _paths_key(path_strings),
                "attrs": item["attrs"],
            }
        )

    parsed_rows, sku_messages = _allocate_skus_by_ref_and_urbyn(
        db, owner_tva, parsed_rows
    )
    errors.extend(sku_messages)
    products_created = 0
    products_updated = 0
    links_created = 0

    for item in parsed_rows:
        sku = (item["sku"] or "").strip()
        if not sku:
            sku = _generate_client_sku(db, owner_tva)
            item["sku"] = sku

        product = repo.find_product_by_client_sku(db, owner_tva, sku)
        if product is None:
            product = repo.create_imported_product(
                db,
                company_tva=owner_tva,
                client_sku=sku,
                product_name=item["name"],
            )
            products_created += 1
        else:
            product.product_name = item["name"]
            product.updated_at = datetime.utcnow()
            products_updated += 1

        repo.upsert_product_description(db, product.id, item["description"])
        repo.upsert_product_price(
            db,
            product_id=product.id,
            price=item["price"],
            currency=item["currency"],
        )
        repo.upsert_free_attributes(db, product.id, item["attrs"])

        for catalog_id in item["leaf_ids"]:
            if repo.link_product_to_catalog(db, catalog_id, product.id):
                links_created += 1

    db.commit()

    return CatalogCsvImportResult(
        mode=mode,
        products_created=products_created,
        products_updated=products_updated,
        catalogs_created=len(created_catalog_ids),
        catalogs_cleared=catalogs_cleared,
        links_created=links_created,
        rows_processed=len(parsed_rows),
        errors=errors,
    )
