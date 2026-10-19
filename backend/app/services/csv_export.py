"""Exports admin CSV_FOURNISSEUR et CSV_ABONNEMENT, même colonnes que l'import.

Le fichier est en UTF-8 (BOM) et séparateur « ; » pour s'ouvrir en colonnes dans Excel.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Catalog, CatalogProduct, Company, Product
from app.repositories import supplier_offers_repo as offers_repo

_OFFERS_HEADERS = [
    "Référence",
    "Nom commercial",
    "Prix référence HT",
    "Coefficient Urbanize",
    "Urbyn",
    "Fournisseur",
    "Délais",
    "QTY",
]

_SUBSCRIPTION_HEADERS = ["Fournisseur", "Abonnement"]


def _fr_number(value: object, places: int) -> str:
    quant = Decimal(str(value)).quantize(Decimal(10) ** -places)
    text = format(quant, "f")
    if places > 2:
        text = text.rstrip("0").rstrip(".") or "0"
    return text.replace(".", ",")


def _catalog_index(db: Session) -> dict[int, tuple[str | None, int | None]]:
    return {
        row.id: (row.name, row.parent_id)
        for row in db.scalars(select(Catalog)).all()
    }


def _links_by_product(db: Session) -> dict[int, list[int]]:
    links: dict[int, list[int]] = {}
    for row in db.scalars(select(CatalogProduct)).all():
        links.setdefault(row.product_id, []).append(row.catalog_id)
    return links


def _urbyn_cell(
    product_id: int,
    links: dict[int, list[int]],
    catalogs: dict[int, tuple[str | None, int | None]],
) -> str:
    paths: list[str] = []
    for catalog_id in links.get(product_id, []):
        parts: list[str] = []
        seen: set[int] = set()
        current: int | None = catalog_id
        while current is not None and current not in seen:
            seen.add(current)
            node = catalogs.get(current)
            if node is None:
                break
            name, parent_id = node
            if name and name.strip():
                parts.append(name.strip())
            current = parent_id
        parts.reverse()
        if parts:
            paths.append("[" + "/".join(parts) + "]")
    return "\n".join(sorted(set(paths)))


def _csv_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def export_supplier_offers_csv(db: Session) -> bytes:
    """Une ligne par offre courante (dernière écriture par fournisseur et produit)."""
    catalogs = _catalog_index(db)
    links = _links_by_product(db)
    products = {p.id: p for p in db.scalars(select(Product)).all()}
    companies = {c.tva_intra_com: c for c in db.scalars(select(Company)).all()}

    rows: list[list[str]] = []
    for offer in offers_repo.latest_offers_all(db):
        product = products.get(offer.product_id)
        company = companies.get(offer.company_tva_intra_com)
        if product is None or company is None:
            continue
        rows.append(
            [
                product.client_sku or "",
                product.product_name,
                _fr_number(offer.price, 2),
                _fr_number(offer.urbyn_marge, 4),
                _urbyn_cell(product.id, links, catalogs),
                company.company_name,
                str(offer.delai_jours),
                str(offer.stock),
            ]
        )
    rows.sort(key=lambda row: (row[5].casefold(), row[1].casefold(), row[0].casefold()))
    return _csv_bytes(_OFFERS_HEADERS, rows)


def export_subscriptions_csv(db: Session) -> bytes:
    """Sociétés qui ont une offre ou un statut d'abonnement."""
    statuses = offers_repo.subscription_map(db)
    offer_tvas = {
        offer.company_tva_intra_com for offer in offers_repo.latest_offers_all(db)
    }
    wanted = offer_tvas | set(statuses)
    companies = [
        company
        for company in db.scalars(select(Company)).all()
        if company.tva_intra_com in wanted
    ]
    companies.sort(key=lambda company: company.company_name.casefold())
    rows = [
        [company.company_name, "True" if statuses.get(company.tva_intra_com) else "False"]
        for company in companies
    ]
    return _csv_bytes(_SUBSCRIPTION_HEADERS, rows)
