"""Classeur APP EXPORT.

Onglets, dans l'ordre :
1. SKU — seule saisie de SKU, nom, chemins Urbyn, prix et coefficient Urbanize
2. Abonnement
3. Fournisseurs — SKU relié par égalité, prix saisis
4. Un onglet par catalogue racine

Les colonnes pilotées (SKU, nom, Urbyn, prix, coefficient) sont des égalités
vers la feuille SKU. L'import lit la valeur : littéral, égalité résolue, ou
résultat déjà calculé par Excel.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    AddressCatalog,
    CartItem,
    Catalog,
    CatalogAttributeDefinition,
    CatalogLink,
    CatalogProduct,
    ClientOrderItem,
    Company,
    CompanySubscription,
    Language,
    Product,
    ProductAttribut,
    ProductMandatoryAttributeValue,
    ProductOrder,
    ProductPriceHistory,
    ProductTranslation,
    SupplierProductPrice,
)
from app.repositories import admin_catalog_repo as catalog_repo
from app.repositories import supplier_offers_repo as offers_repo
from app.schemas.admin import AppExcelImportResult, CatalogCsvImportRowError
from app.services.admin import AdminError
from app.services.csv_utils import (
    normalize_name,
    parse_bool,
    parse_decimal,
    parse_int,
    parse_urbyn_paths,
)

SHEET_SKU = "SKU"
SHEET_SUB = "Abonnement"
SHEET_OFFERS = "Fournisseurs"
_RESERVED = {SHEET_SKU.casefold(), SHEET_SUB.casefold(), SHEET_OFFERS.casefold(), "fournisseur"}

SKU_HEADERS = [
    "SKU",
    "Nom commercial",
    "Urbyn",
    "Prix référence HT",
    "Coefficient Urbanize",
]
CATALOG_FIXED = [
    "SKU",
    "Référence",
    "Nom commercial",
    "Description",
    "Prix référence HT",
    "Coefficient Urbanize",
    "Délais",
    "Unité",
    "Urbyn",
    "Fournisseur",
    "Fichier source",
]
OFFER_HEADERS = [
    "SKU",
    "Fournisseur",
    "Prix référence HT",
    "Coefficient Urbanize",
    "Délais",
    "QTY",
]
SUB_HEADERS = ["Fournisseur", "Abonnement"]

_SKU_CELL = {
    "SKU": "A",
    "Nom commercial": "B",
    "Urbyn": "C",
    "Prix référence HT": "D",
    "Coefficient Urbanize": "E",
}
_DRIVEN = set(_SKU_CELL)

_ATTR_SKIP = {
    "référence",
    "reference",
    "unité",
    "unite",
    "fournisseur (csv)",
    "description",
    "fichier source",
}

_HEADER_FILL = PatternFill("solid", fgColor="111111")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_FORMULA_FILL = PatternFill("solid", fgColor="FFF4CC")
_TITLE_FONT = Font(bold=True, color="111111")
_WRAP = Alignment(wrap_text=True, vertical="center")

_CELL_REF = re.compile(
    r"""^=\s*(?:'(?P<quoted>(?:[^']|'')+)'|(?P<plain>[A-Za-z_][A-Za-z0-9_. ]*))!\s*\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d+)\s*$"""
)
_BAD_SHEET = re.compile(r"[:\\/?*\[\]]")
_MAX_ERRORS = 150


@dataclass
class _SkuRow:
    row: int
    sku: str
    name: str
    paths: list[list[str]]
    price: Decimal
    coef: Decimal


@dataclass
class _CatalogRow:
    sheet: str
    row: int
    root: str
    sku: str
    reference: str
    name: str
    description: str
    price: Decimal
    coef: Decimal
    delai: int
    unit: str
    paths: list[list[str]]
    supplier_label: str
    source_file: str
    attrs: dict[str, str]


@dataclass
class _OfferRow:
    row: int
    sku: str
    supplier: str
    price: Decimal
    coef: Decimal
    delai: int
    qty: int


@dataclass
class _SubRow:
    row: int
    supplier: str
    abonne: bool


@dataclass
class _Parsed:
    skus: list[_SkuRow] = field(default_factory=list)
    catalogs: list[_CatalogRow] = field(default_factory=list)
    offers: list[_OfferRow] = field(default_factory=list)
    subscriptions: list[_SubRow] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)


def export_app_excel(db: Session) -> bytes:
    catalogs = list(db.scalars(select(Catalog)).all())
    by_id = {c.id: c for c in catalogs}
    roots = [c for c in catalogs if c.parent_id is None or c.parent_id == c.id]
    roots.sort(key=lambda c: (c.name or "").casefold())

    links: dict[int, list[int]] = defaultdict(list)
    for link in db.scalars(select(CatalogProduct)).all():
        links[link.product_id].append(link.catalog_id)

    product_ids = list(links)
    products = {
        p.id: p
        for p in db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    } if product_ids else {}

    seen_sku: dict[str, int] = {}
    for product in products.values():
        sku = (product.client_sku or "").strip()
        if not sku:
            raise AdminError(
                "missing_sku",
                f"Le produit « {product.product_name} » n'a pas de SKU (client_sku).",
            )
        key = sku.casefold()
        if key in seen_sku:
            raise AdminError(
                "duplicate_sku",
                f"SKU « {sku} » porté par plusieurs produits du catalogue.",
            )
        seen_sku[key] = product.id

    attrs = _attributes_by_product(db, product_ids)
    descriptions = _descriptions_by_product(db, product_ids)
    urbanize = catalog_repo.ensure_urbanize_company(db)
    urbanize_offers = {
        offer.product_id: offer
        for offer in offers_repo.latest_offers_for_company(db, urbanize.tva_intra_com)
        if offer.product_id in products
    }
    companies = {c.tva_intra_com: c for c in db.scalars(select(Company)).all()}

    records: list[dict] = []
    for product_id, product in products.items():
        paths: list[list[str]] = []
        for catalog_id in links.get(product_id, []):
            segments = _path_of(catalog_id, by_id)
            if segments:
                paths.append(segments)
        unique = _unique_paths(paths)
        if not unique:
            continue
        offer = urbanize_offers.get(product_id)
        price = Decimal(str(offer.price)) if offer is not None else Decimal("0")
        coef = Decimal(str(offer.urbyn_marge)) if offer is not None else Decimal("1")
        delai = int(offer.delai_jours) if offer is not None else 0
        currency = (offer.currency if offer is not None else "EUR") or "EUR"
        product_attrs = dict(attrs.get(product_id, {}))
        records.append(
            {
                "product": product,
                "paths": unique,
                "roots": {p[0] for p in unique},
                "price": price,
                "coef": coef,
                "delai": delai,
                "currency": currency,
                "description": descriptions.get(product_id, ""),
                "attrs": product_attrs,
                "reference": _pop_attr(product_attrs, "référence", "reference"),
                "unit_label": _pop_attr(product_attrs, "unité", "unite"),
                "supplier_label": _pop_attr(product_attrs, "fournisseur (csv)")
                or (
                    companies.get(product.company_tva_intra_com).company_name
                    if companies.get(product.company_tva_intra_com)
                    else ""
                ),
                "source_file": _pop_attr(product_attrs, "fichier source"),
            }
        )

    records.sort(key=lambda rec: ((rec["product"].product_name or "").casefold(), rec["product"].client_sku.casefold()))

    wb = Workbook()
    used_titles = set(_RESERVED)
    sku_ws = wb.active
    sku_ws.title = SHEET_SKU
    _write_header(sku_ws, SKU_HEADERS)
    sku_ws.sheet_properties.tabColor = "111111"
    for index, rec in enumerate(records):
        excel_row = index + 2
        product = rec["product"]
        sku_ws.cell(excel_row, 1, (product.client_sku or "").strip())
        sku_ws.cell(excel_row, 2, product.product_name)
        urbyn_cell = sku_ws.cell(excel_row, 3, _format_paths(rec["paths"]))
        urbyn_cell.alignment = _WRAP
        price_cell = sku_ws.cell(excel_row, 4, float(rec["price"].quantize(Decimal("0.01"))))
        price_cell.number_format = "0.00"
        coef_cell = sku_ws.cell(excel_row, 5, float(rec["coef"].quantize(Decimal("0.0001"))))
        coef_cell.number_format = "0.0000"
    _size_columns(sku_ws, [28, 42, 55, 20, 22])
    sku_ws.auto_filter.ref = f"A1:E{max(1, len(records) + 1)}"
    sku_ws.freeze_panes = "A2"
    sku_ws.row_dimensions[1].height = 22

    sub_ws = wb.create_sheet(SHEET_SUB)
    sub_ws.sheet_properties.tabColor = "1D4ED8"
    _write_header(sub_ws, SUB_HEADERS)
    statuses = offers_repo.subscription_map(db)
    offer_tvas = {offer.company_tva_intra_com for offer in offers_repo.latest_offers_all(db)}
    sub_companies = [
        company
        for company in companies.values()
        if company.tva_intra_com in offer_tvas or company.tva_intra_com in statuses
    ]
    sub_companies.sort(key=lambda company: company.company_name.casefold())
    for index, company in enumerate(sub_companies):
        abonne = False if company.tva_intra_com == urbanize.tva_intra_com else bool(statuses.get(company.tva_intra_com))
        sub_ws.cell(index + 2, 1, company.company_name)
        sub_ws.cell(index + 2, 2, abonne)
    _size_columns(sub_ws, [42, 18])
    sub_ws.freeze_panes = "A2"
    sub_ws.auto_filter.ref = f"A1:B{max(1, len(sub_companies) + 1)}"

    offer_ws = wb.create_sheet(SHEET_OFFERS)
    offer_ws.sheet_properties.tabColor = "B45309"
    _write_header(offer_ws, OFFER_HEADERS)
    sku_row_of = {
        (rec["product"].client_sku or "").strip().casefold(): index + 2
        for index, rec in enumerate(records)
    }
    supplier_rows: list[tuple[str, str, object]] = []
    for offer in offers_repo.latest_offers_all(db):
        if offer.company_tva_intra_com == urbanize.tva_intra_com:
            continue
        product = products.get(offer.product_id)
        if product is None:
            continue
        sku_key = (product.client_sku or "").strip().casefold()
        if sku_key not in sku_row_of:
            continue
        company = companies.get(offer.company_tva_intra_com)
        if company is None:
            continue
        supplier_rows.append((company.company_name.casefold(), sku_key, offer))
    supplier_rows.sort(key=lambda item: (item[0], item[1]))
    for index, (_, sku_key, offer) in enumerate(supplier_rows):
        excel_row = index + 2
        master = sku_row_of[sku_key]
        sku_cell = offer_ws.cell(excel_row, 1, f"={SHEET_SKU}!A{master}")
        sku_cell.fill = _FORMULA_FILL
        company = companies[offer.company_tva_intra_com]
        offer_ws.cell(excel_row, 2, company.company_name)
        price_cell = offer_ws.cell(excel_row, 3, float(Decimal(str(offer.price)).quantize(Decimal("0.01"))))
        price_cell.number_format = "0.00"
        coef_cell = offer_ws.cell(excel_row, 4, float(Decimal(str(offer.urbyn_marge)).quantize(Decimal("0.0001"))))
        coef_cell.number_format = "0.0000"
        offer_ws.cell(excel_row, 5, int(offer.delai_jours))
        offer_ws.cell(excel_row, 6, int(offer.stock))
    _size_columns(offer_ws, [28, 36, 20, 22, 12, 10])
    offer_ws.freeze_panes = "A2"
    offer_ws.auto_filter.ref = f"A1:F{max(1, len(supplier_rows) + 1)}"

    for root in roots:
        root_name = (root.name or "").strip() or f"Catalogue {root.id}"
        title = _sheet_title(root_name, used_titles)
        ws = wb.create_sheet(title)
        ws.sheet_properties.tabColor = "64748B"
        ws["A1"] = "Racine"
        ws["A1"].font = _TITLE_FONT
        ws["B1"] = root_name
        ws["B1"].font = _TITLE_FONT
        group = [rec for rec in records if root_name in rec["roots"]]
        attr_names = sorted(
            {name for rec in group for name in rec["attrs"] if name.casefold() not in _ATTR_SKIP},
            key=str.casefold,
        )
        headers = CATALOG_FIXED + attr_names
        _write_header(ws, headers, row=2)
        for index, rec in enumerate(group):
            excel_row = index + 3
            master = sku_row_of[(rec["product"].client_sku or "").strip().casefold()]
            values = {
                "Référence": rec["reference"],
                "Description": rec["description"],
                "Délais": rec["delai"],
                "Unité": rec["unit_label"] or rec["currency"],
                "Fournisseur": rec["supplier_label"],
                "Fichier source": rec["source_file"],
            }
            for col, header in enumerate(headers, start=1):
                if header in _DRIVEN:
                    cell = ws.cell(excel_row, col, f"={SHEET_SKU}!{_SKU_CELL[header]}{master}")
                    cell.fill = _FORMULA_FILL
                    if header == "Prix référence HT":
                        cell.number_format = "0.00"
                    elif header == "Coefficient Urbanize":
                        cell.number_format = "0.0000"
                    elif header == "Urbyn":
                        cell.alignment = _WRAP
                elif header in values:
                    ws.cell(excel_row, col, values[header])
                else:
                    text = rec["attrs"].get(header, "")
                    if text:
                        ws.cell(excel_row, col, text)
        widths = [28, 22, 42, 36, 20, 22, 12, 12, 55, 28, 22] + [18] * len(attr_names)
        _size_columns(ws, widths)
        last_col = get_column_letter(len(headers))
        ws.freeze_panes = "A3"
        ws.auto_filter.ref = f"A2:{last_col}{max(2, len(group) + 2)}"
        ws.row_dimensions[1].height = 20

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def import_app_excel(db: Session, content: bytes) -> AppExcelImportResult:
    parsed, errors = _parse(content)
    result = AppExcelImportResult(sku_rows=len(parsed.skus), errors=errors)
    if errors:
        return result

    try:
        counts = _apply(db, parsed)
        db.commit()
    except AdminError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    result.applied = True
    result.products_written = counts["products_written"]
    result.products_deleted = counts["products_deleted"]
    result.catalogs_deleted = counts["catalogs_deleted"]
    result.offers_written = counts["offers_written"]
    result.subscriptions_written = counts["subscriptions_written"]
    return result


def _parse(content: bytes) -> tuple[_Parsed, list[CatalogCsvImportRowError]]:
    errors: list[CatalogCsvImportRowError] = []
    try:
        wb = load_workbook(io.BytesIO(content), data_only=False)
        wb_values = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:
        raise AdminError("invalid_excel", "Le fichier n'est pas un classeur Excel lisible.") from exc

    sheets = {ws.title: _matrix(ws) for ws in wb.worksheets}
    cached = {ws.title: _matrix(ws) for ws in wb_values.worksheets}
    parsed = _Parsed()

    sku_title = _find_sheet(sheets, SHEET_SKU)
    sub_title = _find_sheet(sheets, SHEET_SUB)
    offer_title = _find_sheet(sheets, SHEET_OFFERS)
    if sku_title is None or sub_title is None or offer_title is None:
        missing = [
            name
            for name, found in (
                (SHEET_SKU, sku_title),
                (SHEET_SUB, sub_title),
                (SHEET_OFFERS, offer_title),
            )
            if found is None
        ]
        raise AdminError(
            "invalid_excel",
            "Onglets obligatoires manquants : " + ", ".join(missing) + ".",
        )

    sku_header = _header_map(_row(sheets, sku_title, 0), SKU_HEADERS, SHEET_SKU, 1, errors)
    if sku_header is not None:
        seen: set[str] = set()
        for offset, raw in enumerate(_data_rows(sheets, sku_title, 1), start=2):
            if _blank(raw):
                continue
            values = _resolved_row(sheets, cached, sku_title, offset - 1, errors, SHEET_SKU)
            sku = _text(_at(values, sku_header["SKU"]))
            name = _text(_at(values, sku_header["Nom commercial"]))
            urbyn = _text(_at(values, sku_header["Urbyn"]))
            price = _money(_at(values, sku_header["Prix référence HT"]))
            coef = _money(_at(values, sku_header["Coefficient Urbanize"]))
            if not sku:
                _err(errors, SHEET_SKU, offset, "SKU vide.")
                continue
            if len(sku) > 100:
                _err(errors, SHEET_SKU, offset, "SKU trop long (100 caractères maximum).")
                continue
            if sku.casefold() in seen:
                _err(errors, SHEET_SKU, offset, f"SKU « {sku} » en double.")
                continue
            seen.add(sku.casefold())
            if not name:
                _err(errors, SHEET_SKU, offset, "Nom commercial vide.")
            elif len(name) > 255:
                _err(errors, SHEET_SKU, offset, "Nom commercial trop long (255 caractères maximum).")
            paths = parse_urbyn_paths(urbyn)
            if not paths:
                _err(errors, SHEET_SKU, offset, "Urbyn vide ou invalide (attendu [Racine/…]).")
            if price is None or price < 0:
                _err(errors, SHEET_SKU, offset, "Prix référence HT invalide.")
                price = Decimal("0")
            if coef is None or coef <= 0:
                _err(errors, SHEET_SKU, offset, "Coefficient Urbanize invalide.")
                coef = Decimal("1")
            parsed.skus.append(
                _SkuRow(
                    row=offset,
                    sku=sku,
                    name=name,
                    paths=paths,
                    price=price.quantize(Decimal("0.01")),
                    coef=coef.quantize(Decimal("0.0001")),
                )
            )

    masters = {row.sku.casefold(): row for row in parsed.skus}

    sub_header = _header_map(_row(sheets, sub_title, 0), SUB_HEADERS, SHEET_SUB, 1, errors)
    if sub_header is not None:
        seen_sub: set[str] = set()
        for offset, raw in enumerate(_data_rows(sheets, sub_title, 1), start=2):
            if _blank(raw):
                continue
            values = _resolved_row(sheets, cached, sub_title, offset - 1, errors, SHEET_SUB)
            supplier = _text(_at(values, sub_header["Fournisseur"]))
            abonne = _as_bool(_at(values, sub_header["Abonnement"]))
            if not supplier:
                _err(errors, SHEET_SUB, offset, "Fournisseur vide.")
                continue
            key = normalize_name(supplier)
            if key in seen_sub:
                _err(errors, SHEET_SUB, offset, f"Fournisseur « {supplier} » en double.")
                continue
            seen_sub.add(key)
            if abonne is None:
                _err(errors, SHEET_SUB, offset, "Abonnement invalide (True/False, Oui/Non, 1/0).")
                continue
            parsed.subscriptions.append(_SubRow(row=offset, supplier=supplier, abonne=abonne))

    offer_header = _header_map(_row(sheets, offer_title, 0), OFFER_HEADERS, SHEET_OFFERS, 1, errors)
    if offer_header is not None:
        seen_offer: set[tuple[str, str]] = set()
        for offset, raw in enumerate(_data_rows(sheets, offer_title, 1), start=2):
            if _blank(raw):
                continue
            values = _resolved_row(sheets, cached, offer_title, offset - 1, errors, SHEET_OFFERS)
            sku = _text(_at(values, offer_header["SKU"]))
            supplier = _text(_at(values, offer_header["Fournisseur"]))
            price = _money(_at(values, offer_header["Prix référence HT"]))
            coef = _money(_at(values, offer_header["Coefficient Urbanize"]))
            delai = _as_int(_at(values, offer_header["Délais"]))
            qty_raw = _at(values, offer_header["QTY"])
            qty = 0 if _text(qty_raw) == "" else _as_int(qty_raw)
            if not sku:
                _err(errors, SHEET_OFFERS, offset, "SKU vide.")
                continue
            master = masters.get(sku.casefold())
            if master is None:
                _err(errors, SHEET_OFFERS, offset, f"SKU « {sku} » absent de la feuille SKU.")
                continue
            if not supplier:
                _err(errors, SHEET_OFFERS, offset, "Fournisseur vide.")
                continue
            pair = (sku.casefold(), normalize_name(supplier))
            if pair in seen_offer:
                _err(errors, SHEET_OFFERS, offset, f"Offre en double pour {sku} / {supplier}.")
                continue
            seen_offer.add(pair)
            if price is None or price < 0:
                _err(errors, SHEET_OFFERS, offset, "Prix référence HT invalide.")
                continue
            if coef is None or coef <= 0:
                _err(errors, SHEET_OFFERS, offset, "Coefficient Urbanize invalide.")
                continue
            if delai is None or delai < 0:
                _err(errors, SHEET_OFFERS, offset, "Délais invalide.")
                continue
            if qty is None or qty < 0:
                _err(errors, SHEET_OFFERS, offset, "QTY invalide.")
                continue
            parsed.offers.append(
                _OfferRow(
                    row=offset,
                    sku=master.sku,
                    supplier=supplier,
                    price=price.quantize(Decimal("0.01")),
                    coef=coef.quantize(Decimal("0.0001")),
                    delai=delai,
                    qty=qty,
                )
            )

    catalog_titles = [
        title
        for title in wb.sheetnames
        if title not in {sku_title, sub_title, offer_title}
    ]
    seen_roots: set[str] = set()
    for title in catalog_titles:
        matrix = sheets[title]
        root = _text(_at(_row(sheets, title, 0), 1))
        marker = normalize_name(_text(_at(_row(sheets, title, 0), 0)))
        if marker != "racine" or not root:
            _err(errors, title, 1, "La cellule A1 doit valoir « Racine » et B1 le nom du catalogue racine.")
            continue
        if normalize_name(root) in seen_roots:
            _err(errors, title, 1, f"Catalogue racine « {root} » déjà présent sur un autre onglet.")
            continue
        seen_roots.add(normalize_name(root))
        parsed.roots.append(root)
        header = _header_map(_row(sheets, title, 1), CATALOG_FIXED, title, 2, errors)
        if header is None:
            continue
        header_labels = [_text(value) for value in _row(sheets, title, 1)]
        seen_on_sheet: set[str] = set()
        for offset, raw in enumerate(_data_rows(sheets, title, 2), start=3):
            if _blank(raw):
                continue
            values = _resolved_row(sheets, cached, title, offset - 1, errors, title)
            sku = _text(_at(values, header["SKU"]))
            if not sku:
                _err(errors, title, offset, "SKU vide.")
                continue
            master = masters.get(sku.casefold())
            if master is None:
                _err(errors, title, offset, f"SKU « {sku} » absent de la feuille SKU.")
                continue
            if sku.casefold() in seen_on_sheet:
                _err(errors, title, offset, f"SKU « {sku} » en double sur cet onglet.")
                continue
            seen_on_sheet.add(sku.casefold())
            name = _text(_at(values, header["Nom commercial"]))
            urbyn = _text(_at(values, header["Urbyn"]))
            price = _money(_at(values, header["Prix référence HT"]))
            coef = _money(_at(values, header["Coefficient Urbanize"]))
            paths = parse_urbyn_paths(urbyn)
            if name and normalize_name(name) != normalize_name(master.name):
                _err(errors, title, offset, f"Nom commercial différent de la feuille SKU pour « {sku} ».")
            if paths and _path_key(paths) != _path_key(master.paths):
                _err(errors, title, offset, f"Chemins Urbyn différents de la feuille SKU pour « {sku} ».")
            if price is not None and price.quantize(Decimal("0.01")) != master.price:
                _err(errors, title, offset, f"Prix référence HT différent de la feuille SKU pour « {sku} ».")
            if coef is not None and coef.quantize(Decimal("0.0001")) != master.coef:
                _err(errors, title, offset, f"Coefficient Urbanize différent de la feuille SKU pour « {sku} ».")
            if not any(normalize_name(path[0]) == normalize_name(root) for path in master.paths if path):
                _err(errors, title, offset, f"Le SKU « {sku} » n'a aucun chemin sous « {root} ».")
            delai = _as_int(_at(values, header["Délais"]))
            if _text(_at(values, header["Délais"])) == "":
                delai = 0
            if delai is None or delai < 0:
                _err(errors, title, offset, "Délais invalide.")
                delai = 0
            fixed_labels = {name.casefold() for name in CATALOG_FIXED}
            extra: dict[str, str] = {}
            for col, label in enumerate(header_labels):
                if not label or label.casefold() in fixed_labels:
                    continue
                text = _text(_at(values, col))
                if text:
                    if len(label) > 120:
                        _err(errors, title, offset, f"Attribut « {label[:40]} » trop long.")
                        continue
                    extra[label] = text
            parsed.catalogs.append(
                _CatalogRow(
                    sheet=title,
                    row=offset,
                    root=root,
                    sku=master.sku,
                    reference=_text(_at(values, header["Référence"])),
                    name=name,
                    description=_text(_at(values, header["Description"])),
                    price=master.price,
                    coef=master.coef,
                    delai=delai,
                    unit=_text(_at(values, header["Unité"])),
                    paths=master.paths,
                    supplier_label=_text(_at(values, header["Fournisseur"])),
                    source_file=_text(_at(values, header["Fichier source"])),
                    attrs=extra,
                )
            )

    _check_catalog_agreement(parsed, errors)
    for row in parsed.skus:
        for segments in row.paths:
            if not segments:
                continue
            if normalize_name(segments[0]) not in seen_roots:
                _err(
                    errors,
                    SHEET_SKU,
                    row.row,
                    f"Le chemin [{'/'.join(segments)}] n'a pas d'onglet catalogue « {segments[0]} ».",
                )
    return parsed, errors[:_MAX_ERRORS]


def _check_catalog_agreement(parsed: _Parsed, errors: list[CatalogCsvImportRowError]) -> None:
    by_sku: dict[str, list[_CatalogRow]] = defaultdict(list)
    for row in parsed.catalogs:
        by_sku[row.sku.casefold()].append(row)
    for rows in by_sku.values():
        descriptions = {row.description.strip() for row in rows if row.description.strip()}
        if len(descriptions) > 1:
            _err(errors, rows[0].sheet, rows[0].row, f"Descriptions différentes pour le SKU « {rows[0].sku} ».")
        delais = {row.delai for row in rows}
        if len(delais) > 1:
            _err(errors, rows[0].sheet, rows[0].row, f"Délais différents pour le SKU « {rows[0].sku} ».")
        units = {row.unit.strip() for row in rows if row.unit.strip()}
        if len(units) > 1:
            _err(errors, rows[0].sheet, rows[0].row, f"Unités différentes pour le SKU « {rows[0].sku} ».")
        attrs: dict[str, tuple[str, _CatalogRow]] = {}
        for row in rows:
            for name, value in row.attrs.items():
                key = name.casefold()
                previous = attrs.get(key)
                if previous is None:
                    attrs[key] = (value, row)
                elif previous[0] != value:
                    _err(
                        errors,
                        row.sheet,
                        row.row,
                        f"Attribut « {name} » différent pour le SKU « {row.sku} ».",
                    )


def _apply(db: Session, parsed: _Parsed) -> dict[str, int]:
    urbanize = catalog_repo.ensure_urbanize_company(db)
    companies = _company_index(db)
    for row in parsed.subscriptions:
        matches = companies.get(normalize_name(row.supplier), [])
        if len(matches) != 1:
            label = "introuvable" if not matches else "ambigu"
            raise AdminError("unknown_supplier", f"Abonnement, ligne {row.row} : fournisseur « {row.supplier} » {label}.")
    for row in parsed.offers:
        matches = companies.get(normalize_name(row.supplier), [])
        if len(matches) != 1:
            label = "introuvable" if not matches else "ambigu"
            raise AdminError("unknown_supplier", f"Fournisseurs, ligne {row.row} : fournisseur « {row.supplier} » {label}.")
        if matches[0].tva_intra_com == urbanize.tva_intra_com:
            raise AdminError(
                "urbanize_offer",
                f"Fournisseurs, ligne {row.row} : le prix Urbanize se règle sur la feuille SKU.",
            )

    initial_ids = set(db.scalars(select(CatalogProduct.product_id).distinct()).all())
    kept_catalog_ids: set[int] = set()
    kept_root_ids: set[int] = set()
    known_catalogs = list(db.scalars(select(Catalog)).all())
    resolved_paths: dict[tuple[str, ...], int] = {}

    def reuse_root(name: str) -> None:
        target = normalize_name(name)
        for catalog in known_catalogs:
            if catalog.parent_id not in (None, catalog.id):
                continue
            if normalize_name(catalog.name or "") == target:
                if catalog.name != name:
                    catalog.name = name
                    catalog.updated_at = datetime.utcnow()
                    db.flush()
                return

    def reuse_child(parent_id: int, name: str) -> None:
        target = normalize_name(name)
        for child in known_catalogs:
            if child.parent_id != parent_id or child.id == parent_id:
                continue
            if normalize_name(child.name or "") == target:
                if child.name != name:
                    child.name = name
                    child.updated_at = datetime.utcnow()
                    db.flush()
                return

    def keep_path(segments: list[str]) -> int:
        key = tuple(segments)
        cached = resolved_paths.get(key)
        if cached is not None:
            return cached
        for index, name in enumerate(segments):
            if index == 0:
                reuse_root(name)
                continue
            parent = next(
                (
                    catalog
                    for catalog in known_catalogs
                    if catalog.parent_id in (None, catalog.id) and catalog.name == segments[0]
                ),
                None,
            )
            for part in segments[1:index]:
                if parent is None:
                    break
                parent_id = parent.id
                parent = next(
                    (
                        catalog
                        for catalog in known_catalogs
                        if catalog.parent_id == parent_id
                        and catalog.id != parent_id
                        and catalog.name == part
                    ),
                    None,
                )
            if parent is not None:
                reuse_child(parent.id, name)
        leaf, _created, chain = catalog_repo.ensure_catalog_path(db, segments)
        for catalog_id in chain:
            if all(catalog.id != catalog_id for catalog in known_catalogs):
                created = db.get(Catalog, catalog_id)
                if created is not None:
                    known_catalogs.append(created)
        kept_catalog_ids.update(chain)
        if chain:
            kept_root_ids.add(chain[0])
        resolved_paths[key] = leaf.id
        return leaf.id

    for root_name in parsed.roots:
        keep_path([root_name])

    by_sku_rows: dict[str, list[_CatalogRow]] = defaultdict(list)
    for row in parsed.catalogs:
        by_sku_rows[row.sku.casefold()].append(row)

    sku_to_product: dict[str, Product] = {}
    products_written = 0
    pool = list(db.scalars(select(Product)).all())

    for master in parsed.skus:
        leaf_ids: list[int] = []
        for segments in master.paths:
            leaf_ids.append(keep_path(segments))
        leaf_ids = list(dict.fromkeys(leaf_ids))
        product = _match_product(pool, master.sku, initial_ids)
        if product is None:
            product = catalog_repo.create_imported_product(
                db,
                company_tva=urbanize.tva_intra_com,
                client_sku=master.sku,
                product_name=master.name,
            )
            pool.append(product)
        else:
            product.client_sku = master.sku
            product.product_name = master.name
            product.is_active = True
            product.updated_at = datetime.utcnow()
        products_written += 1
        sku_to_product[master.sku.casefold()] = product

        sheet_rows = by_sku_rows.get(master.sku.casefold(), [])
        description = next((row.description.strip() for row in sheet_rows if row.description.strip()), "")
        delai = sheet_rows[0].delai if sheet_rows else 0
        unit = next((row.unit.strip() for row in sheet_rows if row.unit.strip()), "EUR")
        currency = unit.upper() if len(unit) == 3 and unit.isalpha() else "EUR"
        attrs: dict[str, str] = {}
        for row in sheet_rows:
            if row.reference:
                attrs["Référence"] = row.reference
            if row.supplier_label:
                attrs["Fournisseur (CSV)"] = row.supplier_label
            if row.source_file:
                attrs["Fichier source"] = row.source_file
            if currency == "EUR" and unit and unit.upper() != "EUR":
                attrs["Unité"] = unit
            attrs.update(row.attrs)
        _replace_attributes(db, product.id, attrs)
        _set_description(db, product.id, description)
        catalog_repo.upsert_product_price(
            db,
            product_id=product.id,
            price=master.price,
            currency=currency,
        )
        offers_repo.append_offer(
            db,
            company_tva=urbanize.tva_intra_com,
            product_id=product.id,
            price=master.price,
            urbyn_marge=master.coef,
            delai_jours=delai,
            stock=0,
            source="app_excel",
            currency=currency,
            skip_if_unchanged=True,
        )
        _replace_links(db, product.id, leaf_ids)

    offers_written = 0
    offers_by_sku: dict[str, list[_OfferRow]] = defaultdict(list)
    for row in parsed.offers:
        offers_by_sku[row.sku.casefold()].append(row)
    for sku_key, product in sku_to_product.items():
        wanted = {companies[normalize_name(row.supplier)][0].tva_intra_com for row in offers_by_sku.get(sku_key, [])}
        existing = set(
            db.scalars(
                select(SupplierProductPrice.company_tva_intra_com).where(
                    SupplierProductPrice.product_id == product.id,
                    SupplierProductPrice.company_tva_intra_com != urbanize.tva_intra_com,
                )
            ).all()
        )
        for tva in existing - wanted:
            offers_repo.delete_offers_for_product(db, tva, product.id)
        for row in offers_by_sku.get(sku_key, []):
            company = companies[normalize_name(row.supplier)][0]
            if offers_repo.append_offer(
                db,
                company_tva=company.tva_intra_com,
                product_id=product.id,
                price=row.price,
                urbyn_marge=row.coef,
                delai_jours=row.delai,
                stock=row.qty,
                source="app_excel",
                skip_if_unchanged=True,
            ):
                offers_written += 1

    offers_repo.clear_subscriptions(db)
    db.flush()
    subscriptions_written = 0
    urbanize_listed = False
    for row in parsed.subscriptions:
        company = companies[normalize_name(row.supplier)][0]
        if company.tva_intra_com == urbanize.tva_intra_com:
            urbanize_listed = True
            abonne = False
        else:
            abonne = row.abonne
        offers_repo.set_subscription(db, company.tva_intra_com, abonne)
        subscriptions_written += 1
    if not urbanize_listed:
        offers_repo.set_subscription(db, urbanize.tva_intra_com, False)
        subscriptions_written += 1
    db.flush()

    kept_product_ids = {product.id for product in sku_to_product.values()}
    to_delete = [pid for pid in initial_ids if pid not in kept_product_ids]
    products_deleted = _delete_products(db, to_delete)
    catalogs_deleted = _delete_absent_catalogs(db, kept_root_ids, kept_catalog_ids)

    return {
        "products_written": products_written,
        "products_deleted": products_deleted,
        "catalogs_deleted": catalogs_deleted,
        "offers_written": offers_written,
        "subscriptions_written": subscriptions_written,
    }


def _delete_products(db: Session, product_ids: list[int]) -> int:
    if not product_ids:
        return 0
    db.execute(delete(CartItem).where(CartItem.product_id.in_(product_ids)))
    db.execute(
        update(ProductOrder).where(ProductOrder.product_id.in_(product_ids)).values(product_id=None)
    )
    db.execute(
        update(ClientOrderItem)
        .where(ClientOrderItem.product_id.in_(product_ids))
        .values(product_id=None)
    )
    db.execute(
        delete(ProductMandatoryAttributeValue).where(
            ProductMandatoryAttributeValue.product_id.in_(product_ids)
        )
    )
    db.execute(delete(ProductAttribut).where(ProductAttribut.product_id.in_(product_ids)))
    db.execute(delete(ProductTranslation).where(ProductTranslation.product_id.in_(product_ids)))
    db.execute(delete(ProductPriceHistory).where(ProductPriceHistory.product_id.in_(product_ids)))
    db.execute(delete(SupplierProductPrice).where(SupplierProductPrice.product_id.in_(product_ids)))
    db.execute(delete(CatalogProduct).where(CatalogProduct.product_id.in_(product_ids)))
    result = db.execute(delete(Product).where(Product.id.in_(product_ids)))
    db.flush()
    return int(result.rowcount or 0)


def _delete_absent_catalogs(db: Session, kept_root_ids: set[int], kept_ids: set[int]) -> int:
    fallback = next(iter(kept_ids), None)
    roots = [
        catalog
        for catalog in db.scalars(select(Catalog)).all()
        if catalog.parent_id is None or catalog.parent_id == catalog.id
    ]
    drop: list[int] = []
    for root in roots:
        descendants = _descendant_ids(db, root.id)
        if root.id not in kept_root_ids:
            drop.extend(descendants)
            drop.append(root.id)
            continue
        for child_id in descendants:
            if child_id not in kept_ids:
                drop.append(child_id)
    # Profondeur : les descendants sont déjà listés avant leur parent.
    seen: set[int] = set()
    ordered = [catalog_id for catalog_id in drop if not (catalog_id in seen or seen.add(catalog_id))]
    if fallback is None and ordered:
        order_count = int(
            db.scalar(
                select(ProductOrder.id).where(ProductOrder.catalog_id.in_(ordered)).limit(1)
            )
            is not None
        )
        if order_count:
            raise AdminError(
                "has_orders",
                "Des commandes sont liées à des catalogues absents du fichier, et le fichier ne contient aucun catalogue de repli.",
            )
    for catalog_id in ordered:
        _delete_catalog_node(db, catalog_id, fallback if catalog_id != fallback else None)
    return len(ordered)


def _delete_catalog_node(db: Session, catalog_id: int, fallback: int | None) -> None:
    if fallback is not None and fallback != catalog_id:
        db.execute(
            update(ProductOrder)
            .where(ProductOrder.catalog_id == catalog_id)
            .values(catalog_id=fallback)
        )
    else:
        linked = db.scalar(
            select(ProductOrder.id).where(ProductOrder.catalog_id == catalog_id).limit(1)
        )
        if linked is not None:
            catalog = db.get(Catalog, catalog_id)
            name = catalog.name if catalog is not None else str(catalog_id)
            raise AdminError(
                "has_orders",
                f"Le catalogue « {name} » est lié à des commandes et ne peut pas être supprimé.",
            )
    definition_ids = list(
        db.scalars(
            select(CatalogAttributeDefinition.id).where(
                CatalogAttributeDefinition.catalog_id == catalog_id
            )
        ).all()
    )
    if definition_ids:
        db.execute(
            delete(ProductMandatoryAttributeValue).where(
                ProductMandatoryAttributeValue.catalog_attribute_definition_id.in_(definition_ids)
            )
        )
        db.execute(
            delete(CatalogAttributeDefinition).where(CatalogAttributeDefinition.id.in_(definition_ids))
        )
    db.execute(delete(AddressCatalog).where(AddressCatalog.catalog_id == catalog_id))
    db.execute(
        delete(CatalogLink).where(
            (CatalogLink.from_catalog_id == catalog_id) | (CatalogLink.to_catalog_id == catalog_id)
        )
    )
    db.execute(delete(CatalogProduct).where(CatalogProduct.catalog_id == catalog_id))
    catalog = db.get(Catalog, catalog_id)
    if catalog is not None:
        catalog.parent_id = None
        db.flush()
        db.delete(catalog)
        db.flush()


def _descendant_ids(db: Session, root_id: int) -> list[int]:
    result: list[int] = []

    def walk(parent_id: int) -> None:
        children = db.scalars(
            select(Catalog).where(Catalog.parent_id == parent_id, Catalog.id != parent_id)
        ).all()
        for child in children:
            walk(child.id)
            result.append(child.id)

    walk(root_id)
    return result


def _match_product(pool: list[Product], sku: str, catalog_ids: set[int]) -> Product | None:
    key = sku.casefold()
    matches = [product for product in pool if (product.client_sku or "").strip().casefold() == key]
    if not matches:
        return None
    linked = [product for product in matches if product.id in catalog_ids]
    if len(linked) == 1:
        return linked[0]
    if len(linked) > 1:
        raise AdminError("duplicate_sku", f"Plusieurs produits du catalogue portent le SKU « {sku} ».")
    if len(matches) == 1:
        return matches[0]
    raise AdminError("duplicate_sku", f"Plusieurs produits portent le SKU « {sku} ».")


def _replace_links(db: Session, product_id: int, catalog_ids: list[int]) -> None:
    wanted = set(catalog_ids)
    existing = set(
        db.scalars(select(CatalogProduct.catalog_id).where(CatalogProduct.product_id == product_id)).all()
    )
    extra = existing - wanted
    if extra:
        db.execute(
            delete(CatalogProduct).where(
                CatalogProduct.product_id == product_id,
                CatalogProduct.catalog_id.in_(extra),
            )
        )
    for catalog_id in wanted - existing:
        catalog_repo.link_product_to_catalog(db, catalog_id, product_id)


def _replace_attributes(db: Session, product_id: int, attrs: dict[str, str]) -> None:
    db.execute(delete(ProductAttribut).where(ProductAttribut.product_id == product_id))
    now = datetime.utcnow()
    for name, value in attrs.items():
        text = (value or "").strip()
        label = " ".join(name.split()).strip()
        if not label or not text:
            continue
        db.add(
            ProductAttribut(
                product_id=product_id,
                name=label[:120],
                value=text,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def _set_description(db: Session, product_id: int, description: str) -> None:
    text = (description or "").strip()
    language_id = catalog_repo._default_language_id(db)
    if language_id is None:
        if text:
            _replace_attributes_merge_description(db, product_id, text)
        return
    existing = db.scalar(
        select(ProductTranslation).where(
            ProductTranslation.product_id == product_id,
            ProductTranslation.language_id == language_id,
        )
    )
    if existing is None:
        if text:
            db.add(
                ProductTranslation(
                    product_id=product_id,
                    language_id=language_id,
                    description=text,
                )
            )
    else:
        existing.description = text or None
        existing.updated_at = datetime.utcnow()
    db.flush()


def _replace_attributes_merge_description(db: Session, product_id: int, text: str) -> None:
    db.add(
        ProductAttribut(
            product_id=product_id,
            name="Description",
            value=text,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.flush()


def _company_index(db: Session) -> dict[str, list[Company]]:
    index: dict[str, list[Company]] = defaultdict(list)
    for company in db.scalars(select(Company)).all():
        index[normalize_name(company.company_name)].append(company)
    return index


def _attributes_by_product(db: Session, product_ids: list[int]) -> dict[int, dict[str, str]]:
    grouped: dict[int, dict[str, str]] = defaultdict(dict)
    if not product_ids:
        return grouped
    for row in db.scalars(select(ProductAttribut).where(ProductAttribut.product_id.in_(product_ids))).all():
        if row.name and row.value:
            grouped[row.product_id][row.name] = row.value
    return grouped


def _descriptions_by_product(db: Session, product_ids: list[int]) -> dict[int, str]:
    if not product_ids:
        return {}
    rows = db.execute(
        select(
            ProductTranslation.product_id,
            ProductTranslation.description,
            Language.code,
            Language.is_default,
        )
        .join(Language, Language.id == ProductTranslation.language_id)
        .where(ProductTranslation.product_id.in_(product_ids))
    ).all()
    best: dict[int, tuple[int, str]] = {}
    for product_id, description, code, is_default in rows:
        if not description:
            continue
        rank = 0 if code == "fr" else 1 if is_default else 2
        current = best.get(product_id)
        if current is None or rank < current[0]:
            best[product_id] = (rank, description)
    return {product_id: description for product_id, (_, description) in best.items()}


def _path_of(catalog_id: int, by_id: dict[int, Catalog]) -> list[str]:
    parts: list[str] = []
    seen: set[int] = set()
    current = by_id.get(catalog_id)
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.name and current.name.strip():
            parts.append(current.name.strip())
        if current.parent_id is None or current.parent_id == current.id:
            break
        current = by_id.get(current.parent_id)
    parts.reverse()
    return parts


def _unique_paths(paths: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[list[str]] = []
    for segments in paths:
        key = tuple(segments)
        if key in seen or not segments:
            continue
        seen.add(key)
        unique.append(segments)
    unique.sort(key=lambda segments: "/".join(segments).casefold())
    return unique


def _format_paths(paths: list[list[str]]) -> str:
    return "\n".join(f"[{'/'.join(segments)}]" for segments in paths)


def _path_key(paths: list[list[str]]) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted((tuple(normalize_name(part) for part in segments) for segments in paths), key=lambda item: "/".join(item)))


def _pop_attr(attrs: dict[str, str], *names: str) -> str:
    wanted = {name.casefold() for name in names}
    for key in list(attrs):
        if key.casefold() in wanted:
            return attrs.pop(key) or ""
    return ""


def _write_header(ws: Worksheet, headers: list[str], row: int = 1) -> None:
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row, col, header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[row].height = 22


def _size_columns(ws: Worksheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _sheet_title(name: str, used: set[str]) -> str:
    cleaned = _BAD_SHEET.sub(" ", name)
    cleaned = " ".join(cleaned.split()).strip() or "Catalogue"
    if len(cleaned) > 31:
        cleaned = cleaned[:31].rstrip()
    base = cleaned
    suffix_n = 2
    while cleaned.casefold() in used:
        suffix = f" {suffix_n}"
        cleaned = (base[: 31 - len(suffix)] + suffix).rstrip()
        suffix_n += 1
    used.add(cleaned.casefold())
    return cleaned


def _matrix(ws: Worksheet) -> list[list[object]]:
    rows: list[list[object]] = []
    for row in ws.iter_rows():
        rows.append([cell.value for cell in row])
    while rows and _blank(rows[-1]):
        rows.pop()
    return rows


def _find_sheet(sheets: dict[str, list[list[object]]], name: str) -> str | None:
    target = name.casefold()
    for title in sheets:
        if title.casefold() == target:
            return title
    return None


def _row(sheets: dict[str, list[list[object]]], title: str, index: int) -> list[object]:
    matrix = sheets.get(title) or []
    if index >= len(matrix):
        return []
    return matrix[index]


def _data_rows(sheets: dict[str, list[list[object]]], title: str, start: int) -> list[list[object]]:
    return (sheets.get(title) or [])[start:]


def _header_map(
    row: list[object],
    required: list[str],
    sheet: str,
    excel_row: int,
    errors: list[CatalogCsvImportRowError],
) -> dict[str, int] | None:
    found: dict[str, tuple[str, int]] = {}
    for index, value in enumerate(row):
        label = _text(value)
        if not label:
            continue
        key = label.casefold()
        if key in found:
            _err(errors, sheet, excel_row, f"Colonne « {label} » en double.")
            return None
        found[key] = (label, index)
    missing = [name for name in required if name.casefold() not in found]
    if missing:
        _err(errors, sheet, excel_row, "Colonnes manquantes : " + ", ".join(missing) + ".")
        return None
    mapped = {name: found[name.casefold()][1] for name in required}
    required_keys = {name.casefold() for name in required}
    for key, (label, index) in found.items():
        if key not in required_keys:
            mapped[label] = index
    return mapped


def _resolved_row(
    sheets: dict[str, list[list[object]]],
    cached: dict[str, list[list[object]]],
    sheet: str,
    row_index: int,
    errors: list[CatalogCsvImportRowError],
    label: str,
) -> list[object]:
    raw = _row(sheets, sheet, row_index)
    resolved: list[object] = []
    for col, value in enumerate(raw):
        try:
            resolved.append(_resolve(sheets, cached, sheet, row_index, col, set()))
        except AdminError as exc:
            _err(errors, label, row_index + 1, exc.message)
            resolved.append(None)
    return resolved


def _resolve(
    sheets: dict[str, list[list[object]]],
    cached: dict[str, list[list[object]]],
    sheet: str,
    row_index: int,
    col_index: int,
    stack: set[tuple[str, int, int]],
) -> object:
    key = (sheet, row_index, col_index)
    if key in stack:
        raise AdminError("formula_cycle", "Formule circulaire.")
    raw = _at(_row(sheets, sheet, row_index), col_index)
    if not isinstance(raw, str) or not raw.startswith("="):
        return raw
    match = _CELL_REF.match(raw.strip())
    if match:
        target_sheet = (match.group("quoted") or match.group("plain") or "").replace("''", "'")
        real_sheet = _find_sheet(sheets, target_sheet)
        if real_sheet is None:
            raise AdminError("formula_ref", f"Formule vers un onglet inconnu : {raw}.")
        col = _column_index(match.group("col"))
        row = int(match.group("row")) - 1
        return _resolve(sheets, cached, real_sheet, row, col, stack | {key})
    cached_value = _at(_row(cached, sheet, row_index), col_index)
    if cached_value is not None:
        return cached_value
    raise AdminError(
        "formula_unsupported",
        "Formule sans valeur calculée. Enregistre le fichier dans Excel, ou saisis la valeur.",
    )


def _column_index(letters: str) -> int:
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _at(row: list[object], index: int | None) -> object:
    if index is None or index < 0 or index >= len(row):
        return None
    return row[index]


def _blank(row: list[object]) -> bool:
    return not any(_text(value) for value in row)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    return str(value).strip()


def _money(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return parse_decimal(str(value))


def _as_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return parse_int(_text(value))


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return parse_bool(_text(value))


def _err(errors: list[CatalogCsvImportRowError], sheet: str, row: int, message: str) -> None:
    if len(errors) >= _MAX_ERRORS:
        return
    errors.append(CatalogCsvImportRowError(line=row, message=f"{sheet} : {message}"))
