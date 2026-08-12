"""Import CSV gros volume → produits + arborescence catalogues (colonne Urbyn)."""

from __future__ import annotations

import csv
import io
import random
import re
import string
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

# Colonnes fixes (avant Urbyn) — le reste = attributs dynamiques
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

    # Pass 1 — collecter les feuilles cibles + créer l'arborescence
    path_cache: dict[str, int] = {}
    created_catalog_ids: set[int] = set()
    leaf_targets: set[int] = set()
    preexisting_leaves: set[int] = set()

    parsed_rows: list[dict[str, Any]] = []
    errors: list[CatalogCsvImportRowError] = []

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
        leaf_ids: list[int] = []
        for segments in paths:
            cache_key = "/".join(segments)
            if cache_key in path_cache:
                leaf_id = path_cache[cache_key]
            else:
                leaf, created_ids = repo.ensure_catalog_path(db, segments)
                leaf_id = leaf.id
                path_cache[cache_key] = leaf_id
                created_catalog_ids.update(created_ids)
            leaf_ids.append(leaf_id)
            leaf_targets.add(leaf_id)
            if leaf_id not in created_catalog_ids:
                preexisting_leaves.add(leaf_id)

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

        # Fournisseur CSV reste informatif (attribut), la société UI prime
        fournisseur = _get(row, "fournisseur")
        if fournisseur:
            attrs.setdefault("Fournisseur (CSV)", fournisseur)

        parsed_rows.append(
            {
                "line": line_no,
                "name": name,
                "sku": _get(row, "référence", "reference"),
                "description": _get(row, "description"),
                "price": _parse_price(_get(row, "prix référence ht", "prix reference ht")),
                "currency": _parse_currency(unit_raw),
                "leaf_ids": list(dict.fromkeys(leaf_ids)),
                "attrs": attrs,
            }
        )

    # Mode destructif : vider les catalogues feuilles déjà existants
    catalogs_cleared = 0
    if mode == CatalogCsvImportMode.destructive:
        to_clear = preexisting_leaves & leaf_targets
        for catalog_id in to_clear:
            repo.clear_catalog_products(db, catalog_id)
            catalogs_cleared += 1

    products_created = 0
    products_updated = 0
    links_created = 0

    for item in parsed_rows:
        sku = (item["sku"] or "").strip()
        if not sku:
            sku = _generate_client_sku(db, owner_tva)

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
