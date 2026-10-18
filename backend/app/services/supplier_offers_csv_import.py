"""CSV_FOURNISSEUR : 1 ligne = 1 produit + 1 fournisseur + prix, coefficient, délai, QTY.

Validation complète avant écriture : une seule erreur bloque tout l'import.
Produit retrouvé par « Nom commercial » dans le(s) catalogue(s) de la colonne Urbyn
(chemins existants uniquement, aucun catalogue ni produit créé).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogProduct, Company, Product
from app.repositories import admin_catalog_repo as catalog_repo
from app.repositories import supplier_offers_repo as offers_repo
from app.schemas.admin import (
    CatalogCsvImportMode,
    CatalogCsvImportRowError,
    SupplierOffersCsvImportResult,
)
from app.services.csv_utils import (
    get_value,
    normalize_name,
    parse_decimal,
    parse_int,
    parse_urbyn_paths,
    read_csv_rows,
    require_headers,
    row_dict,
)

_REQUIRED_HEADERS = {
    "Nom commercial": ("nom commercial",),
    "Prix référence HT": ("prix référence ht", "prix reference ht"),
    "Coefficient Urbanize": ("coefficient urbanize",),
    "Urbyn": ("urbyn",),
    "Fournisseur": ("fournisseur",),
    "Délais": ("délais", "delais"),
}


@dataclass
class _OfferRow:
    line: int
    company_tva: str
    product_id: int
    price: Decimal
    coef: Decimal
    delai: int
    stock: int


def _company_index(db: Session) -> dict[str, list[Company]]:
    index: dict[str, list[Company]] = {}
    for company in db.scalars(select(Company)).all():
        index.setdefault(normalize_name(company.company_name), []).append(company)
    return index


def _resolve_catalog(db: Session, segments: list[str]):
    current = catalog_repo._find_root_by_name(db, segments[0])
    for name in segments[1:]:
        if current is None:
            return None
        current = catalog_repo._find_child_by_name(db, current.id, name)
    return current


class _ProductFinder:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._catalog_cache: dict[str, int | None] = {}
        self._products_cache: dict[int, list[Product]] = {}

    def catalog_id(self, segments: list[str]) -> int | None:
        key = "/".join(segments)
        if key not in self._catalog_cache:
            catalog = _resolve_catalog(self.db, segments)
            self._catalog_cache[key] = catalog.id if catalog else None
        return self._catalog_cache[key]

    def products_in(self, catalog_id: int) -> list[Product]:
        if catalog_id not in self._products_cache:
            self._products_cache[catalog_id] = list(
                self.db.scalars(
                    select(Product)
                    .join(CatalogProduct, CatalogProduct.product_id == Product.id)
                    .where(CatalogProduct.catalog_id == catalog_id)
                ).all()
            )
        return self._products_cache[catalog_id]


def import_supplier_offers_csv(
    db: Session, *, content: bytes, mode: CatalogCsvImportMode
) -> SupplierOffersCsvImportResult:
    rows = read_csv_rows(content)
    headers = rows[0]
    require_headers(headers, _REQUIRED_HEADERS)

    companies = _company_index(db)
    finder = _ProductFinder(db)
    errors: list[CatalogCsvImportRowError] = []
    offers: list[_OfferRow] = []
    seen_pairs: dict[tuple[str, int], int] = {}

    def fail(line: int, message: str) -> None:
        errors.append(CatalogCsvImportRowError(line=line, message=message))

    for line_no, raw in enumerate(rows[1:], start=2):
        if not any((c or "").strip() for c in raw):
            continue
        row = row_dict(headers, raw)
        name = get_value(row, "nom commercial")
        supplier_name = get_value(row, "fournisseur")
        reference = get_value(row, "référence", "reference")
        line_ok = True

        matches = companies.get(normalize_name(supplier_name), []) if supplier_name else []
        company: Company | None = None
        if not supplier_name:
            fail(line_no, "Fournisseur vide.")
            line_ok = False
        elif not matches:
            fail(line_no, f"Fournisseur « {supplier_name} » introuvable en base.")
            line_ok = False
        elif len(matches) > 1:
            tvas = ", ".join(c.tva_intra_com for c in matches)
            fail(line_no, f"Fournisseur « {supplier_name} » ambigu ({tvas}).")
            line_ok = False
        else:
            company = matches[0]

        price = parse_decimal(get_value(row, "prix référence ht", "prix reference ht"))
        if price is None or price < 0:
            fail(line_no, "Prix référence HT vide ou invalide.")
            line_ok = False
        coef = parse_decimal(get_value(row, "coefficient urbanize"))
        if coef is None or coef <= 0:
            fail(line_no, "Coefficient Urbanize vide ou invalide.")
            line_ok = False
        delai = parse_int(get_value(row, "délais", "delais"))
        if delai is None or delai < 0:
            fail(line_no, "Délais vide ou invalide (nombre entier de jours attendu).")
            line_ok = False
        qty_raw = get_value(row, "qty")
        stock = parse_int(qty_raw) if qty_raw else 0
        if stock is None or stock < 0:
            fail(line_no, "QTY invalide (nombre entier attendu).")
            line_ok = False

        product: Product | None = None
        paths = parse_urbyn_paths(get_value(row, "urbyn"))
        if not name:
            fail(line_no, "Nom commercial vide.")
            line_ok = False
        elif not paths:
            fail(line_no, "Colonne Urbyn vide ou invalide (attendu [Racine/…/Feuille]).")
            line_ok = False
        else:
            target = normalize_name(name)
            candidates: dict[int, Product] = {}
            for segments in paths:
                catalog_id = finder.catalog_id(segments)
                if catalog_id is None:
                    fail(line_no, f"Catalogue introuvable : [{'/'.join(segments)}].")
                    line_ok = False
                    continue
                for p in finder.products_in(catalog_id):
                    if normalize_name(p.product_name) == target:
                        candidates[p.id] = p
            if len(candidates) > 1 and reference:
                ref = reference.strip().upper()
                candidates = {
                    pid: p
                    for pid, p in candidates.items()
                    if (p.client_sku or "").upper() == ref
                    or (p.client_sku or "").upper().startswith(f"{ref}-")
                }
            if line_ok and not candidates:
                fail(line_no, f"Produit « {name} » introuvable dans le(s) catalogue(s) Urbyn.")
                line_ok = False
            elif len(candidates) > 1:
                fail(
                    line_no,
                    f"Produit « {name} » ambigu ({len(candidates)} produits) — préciser la Référence.",
                )
                line_ok = False
            elif candidates:
                product = next(iter(candidates.values()))

        if not line_ok or company is None or product is None:
            continue

        pair = (company.tva_intra_com, product.id)
        if pair in seen_pairs:
            fail(
                line_no,
                f"Doublon fournisseur/produit (déjà ligne {seen_pairs[pair]}).",
            )
            continue
        seen_pairs[pair] = line_no
        offers.append(
            _OfferRow(
                line=line_no,
                company_tva=company.tva_intra_com,
                product_id=product.id,
                price=price,
                coef=coef,
                delai=delai,
                stock=stock,
            )
        )

    supplier_tvas = sorted({o.company_tva for o in offers})
    result = SupplierOffersCsvImportResult(
        mode=mode,
        rows_processed=len(offers),
        suppliers=supplier_tvas,
        errors=errors,
    )
    if errors:
        return result

    if mode == CatalogCsvImportMode.destructive:
        result.offers_deleted = offers_repo.delete_offers_for_companies(db, supplier_tvas)

    for offer in offers:
        written = offers_repo.append_offer(
            db,
            company_tva=offer.company_tva,
            product_id=offer.product_id,
            price=offer.price,
            urbyn_marge=offer.coef,
            delai_jours=offer.delai,
            stock=offer.stock,
            source="csv_fournisseur",
            skip_if_unchanged=mode == CatalogCsvImportMode.additive,
        )
        if written:
            result.offers_written += 1
        else:
            result.offers_unchanged += 1

    db.commit()
    result.applied = True
    return result
