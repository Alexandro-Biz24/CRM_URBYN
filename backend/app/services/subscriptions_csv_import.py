"""CSV_ABONNEMENT : « Fournisseur » + « Abonnement » (vrai/faux).

Validation complète avant écriture. URBANIZE est toujours forcé à non abonné.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company
from app.repositories import admin_catalog_repo as catalog_repo
from app.repositories import supplier_offers_repo as offers_repo
from app.schemas.admin import (
    CatalogCsvImportMode,
    CatalogCsvImportRowError,
    SubscriptionsCsvImportResult,
)
from app.services.csv_utils import (
    get_value,
    normalize_name,
    parse_bool,
    read_csv_rows,
    require_headers,
    row_dict,
)

_REQUIRED_HEADERS = {
    "Fournisseur": ("fournisseur",),
    "Abonnement": ("abonnement",),
}


def import_subscriptions_csv(
    db: Session, *, content: bytes, mode: CatalogCsvImportMode
) -> SubscriptionsCsvImportResult:
    rows = read_csv_rows(content)
    headers = rows[0]
    require_headers(headers, _REQUIRED_HEADERS)

    urbanize_tva = catalog_repo.ensure_urbanize_company(db).tva_intra_com
    companies: dict[str, list[Company]] = {}
    for company in db.scalars(select(Company)).all():
        companies.setdefault(normalize_name(company.company_name), []).append(company)

    result = SubscriptionsCsvImportResult(mode=mode)
    statuses: dict[str, tuple[bool, int]] = {}

    for line_no, raw in enumerate(rows[1:], start=2):
        if not any((c or "").strip() for c in raw):
            continue
        row = row_dict(headers, raw)
        supplier_name = get_value(row, "fournisseur")
        abonne = parse_bool(get_value(row, "abonnement"))
        matches = companies.get(normalize_name(supplier_name), []) if supplier_name else []

        if not supplier_name:
            result.errors.append(CatalogCsvImportRowError(line=line_no, message="Fournisseur vide."))
            continue
        if not matches:
            result.errors.append(
                CatalogCsvImportRowError(
                    line=line_no, message=f"Fournisseur « {supplier_name} » introuvable en base."
                )
            )
            continue
        if len(matches) > 1:
            tvas = ", ".join(c.tva_intra_com for c in matches)
            result.errors.append(
                CatalogCsvImportRowError(
                    line=line_no, message=f"Fournisseur « {supplier_name} » ambigu ({tvas})."
                )
            )
            continue
        if abonne is None:
            result.errors.append(
                CatalogCsvImportRowError(
                    line=line_no,
                    message="Abonnement invalide (attendu True/False, Oui/Non, 1/0).",
                )
            )
            continue

        tva = matches[0].tva_intra_com
        if tva == urbanize_tva and abonne:
            result.warnings.append(
                CatalogCsvImportRowError(
                    line=line_no, message="URBANIZE ne peut pas être abonné → forcé à False."
                )
            )
            abonne = False
        if tva in statuses and statuses[tva][0] != abonne:
            result.errors.append(
                CatalogCsvImportRowError(
                    line=line_no,
                    message=f"Statut contradictoire avec la ligne {statuses[tva][1]}.",
                )
            )
            continue
        statuses[tva] = (abonne, line_no)

    result.rows_processed = len(statuses)
    if result.errors:
        return result

    if mode == CatalogCsvImportMode.destructive:
        result.subscriptions_deleted = offers_repo.clear_subscriptions(db)
        db.expunge_all()

    for tva, (abonne, _line) in statuses.items():
        if offers_repo.set_subscription(db, tva, abonne):
            result.subscriptions_created += 1
        else:
            result.subscriptions_updated += 1

    if urbanize_tva not in statuses:
        offers_repo.set_subscription(db, urbanize_tva, False)

    db.commit()
    result.applied = True
    return result
