#!/usr/bin/env python3
"""
Remplissage de la DB via API V2 (clients/fournisseurs) a partir de OLD_DATA.

Strategie V2 (par ligne companies_raw):
1) POST avec existing_company.company_id = TVA (donnee reelle ou synthetique stable)
2) Si 400 "Company introuvable..." -> POST avec new_company (creation boite + adresse)

Alternance supplier / client. Pas de produits/catalogues.

Options:
- --dry-run : aucun appel HTTP
- --dry-limit N : raccourci pour dry-run + --limit N (pour tests rapides)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib import error, request


PREFIX = "factice"
# domaine utilisable par EmailStr (pydantic) : eviter .test / .example / .invalid (TLD reserves)
DEFAULT_EMAIL_DOMAIN = "urbanize-factice.site"
DEFAULT_PASSWORD = "Factice#2026"
DEFAULT_LANGUAGE_ID = 1
DEFAULT_TIMEOUT_SECONDS = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Injecte des profils client/fournisseur via les APIs V2 (existing puis new)."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000/api/v1",
        help="Base URL de l'API (defaut: http://127.0.0.1:8000/api/v1)",
    )
    parser.add_argument(
        "--companies-raw-path",
        default=str(
            Path(__file__).resolve().parents[1]
            / "OLD_DATA"
            / "sellsy_full_export"
            / "companies_raw.json"
        ),
        help="Chemin absolu/relatif vers companies_raw.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Nombre max de profils utilisateur crees avec succes",
    )
    parser.add_argument(
        "--dry-limit",
        type=int,
        default=None,
        metavar="N",
        help="Equivaut a --dry-run --limit N (pratique pour tester sans ecrire)",
    )
    parser.add_argument(
        "--email-domain",
        default=DEFAULT_EMAIL_DOMAIN,
        help=(
            "Domaine des emails factices utilisateur / fallback societe "
            f"(defaut: {DEFAULT_EMAIL_DOMAIN}). "
            "Eviter example.test : EmailStr le rejette (TLD reserve)."
        ),
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=None,
        help=(
            "Nombre max de lignes source tentees (arrete avant la fin du fichier si echecs). "
            "Defaut: max(200, limit * 40)."
        ),
    )
    parser.add_argument(
        "--language-id",
        type=int,
        default=DEFAULT_LANGUAGE_ID,
        help="language_id a injecter dans user_profiles",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout HTTP par requete (secondes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'envoie pas les requetes HTTP, affiche uniquement ce qui serait fait",
    )
    ns = parser.parse_args()
    if ns.dry_limit is not None:
        ns.dry_run = True
        ns.limit = ns.dry_limit
    return ns


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
    return slug or "company"


def compact(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    as_text = str(value).strip()
    return as_text if as_text else fallback


def normalize_identifier(value: str, max_len: int = 64) -> str:
    """Espaces et format Sellsy (ex. TVA avec espaces) -> une seule chaine sans espaces."""
    return re.sub(r"\s+", "", value.strip())[:max_len]


def build_company_tva(company: dict[str, Any], index: int) -> str:
    """TVA stable par ligne (raw legal_france.vat ou synthetique). C'est la PK company cote API."""
    legal = company.get("legal_france") or {}
    vat = compact(legal.get("vat"), "")
    if vat:
        return normalize_identifier(vat)
    company_id = compact(company.get("id"), str(index))
    return normalize_identifier(f"FR{PREFIX.upper()}{company_id}")


def build_fake_siret(company: dict[str, Any], index: int) -> str:
    legal = company.get("legal_france") or {}
    siret = compact(legal.get("siret"), "")
    if siret:
        return normalize_identifier(siret, max_len=64)
    company_id = re.sub(r"[^0-9]", "", compact(company.get("id"), str(index)))
    padded = (company_id + "0" * 14)[:14]
    return padded


def build_email(
    company: dict[str, Any], role: str, company_index: int, email_domain: str
) -> str:
    company_id = compact(company.get("id"), str(company_index))
    slug = sanitize_slug(compact(company.get("name"), f"company-{company_id}"))
    domain = email_domain.strip().lstrip("@")
    return f"{PREFIX}.{role}.{company_id}.{slug}@{domain}"


def build_new_company_payload(
    company: dict[str, Any],
    company_index: int,
    tva_intra_com: str,
    email_domain: str,
) -> dict[str, Any]:
    legal = company.get("legal_france") or {}
    siret = build_fake_siret(company, company_index)

    name = compact(company.get("name"), f"{PREFIX} company {company_index}")
    phone = compact(company.get("phone_number"), f"+330100000{company_index % 10}")
    domain = email_domain.strip().lstrip("@")
    email = company_email_for_api(
        company.get("email"),
        f"{PREFIX}.company.{company_index}@{domain}",
    )
    website = compact(company.get("website"), f"https://{PREFIX}-{company_index}.test")
    code_naf = compact(legal.get("ape_naf_code"), "0000Z")
    city = compact((company.get("main_address") or {}).get("city"), "Paris")
    zip_code = compact((company.get("main_address") or {}).get("zip_code"), "75001")
    country = compact((company.get("main_address") or {}).get("country_code"), "FR")

    return {
        "tva_intra_com": normalize_identifier(tva_intra_com),
        "company_name": f"{PREFIX}_{name}"[:255],
        "phone_number": phone,
        "code_naf": code_naf,
        "email": email,
        "condition_reglement": "30 jours fin de mois",
        "branche": compact(company.get("business_segment"), "B2B"),
        "extrait_kbis": f"{PREFIX}_kbis_non_disponible",
        "cgv_accepted": True,
        "website": website,
        "description": (
            f"{PREFIX} profile genere depuis OLD_DATA Sellsy (legacy_id={company.get('id')})."
        )[:512],
        "logo": f"{PREFIX}_logo_placeholder",
        "vat_rate": 20.0,
        "address": {
            "type": "headquarter",
            "street": f"{company_index} rue {PREFIX}",
            "city": city,
            "zip_code": zip_code,
            "state": "Ile-de-France",
            "country_code": country,
            "siret": siret,
            "intra_com": normalize_identifier(tva_intra_com),
            "lat": 48.8566,
            "lng": 2.3522,
            "is_primary": True,
        },
    }


def build_user_fields(
    company: dict[str, Any],
    company_index: int,
    role: str,
    language_id: int,
    phone_for_fixe: str,
    email_domain: str,
) -> dict[str, Any]:
    legacy_id = compact(company.get("id"), str(company_index))
    company_name = compact(company.get("name"), f"company-{legacy_id}")
    user_email = build_email(company, role, company_index, email_domain)
    mobile_suffix = company_index % (10**8)
    return {
        "email": user_email,
        "password": DEFAULT_PASSWORD,
        "mobile_phone": f"+336{mobile_suffix:08d}"[:16],
        "fixe_phone": phone_for_fixe,
        "language_id": language_id,
        "first_name": f"{PREFIX}_{role}_{legacy_id}"[:80],
        "last_name": sanitize_slug(company_name).replace("-", "_")[:80] or "legacy_company",
        "title": "M.",
    }


def build_payload_existing(
    company: dict[str, Any],
    company_index: int,
    role: str,
    language_id: int,
    company_tva: str,
    email_domain: str,
) -> dict[str, Any]:
    phone = compact(company.get("phone_number"), f"+330100000{company_index % 10}")
    base = build_user_fields(
        company, company_index, role, language_id, phone_for_fixe=phone, email_domain=email_domain
    )
    return {
        **base,
        "existing_company": {"company_id": normalize_identifier(company_tva)},
        "new_company": None,
    }


def build_payload_new(
    company: dict[str, Any],
    company_index: int,
    role: str,
    language_id: int,
    company_tva: str,
    email_domain: str,
) -> dict[str, Any]:
    nc = build_new_company_payload(company, company_index, company_tva, email_domain)
    base = build_user_fields(
        company,
        company_index,
        role,
        language_id,
        phone_for_fixe=nc["phone_number"],
        email_domain=email_domain,
    )
    return {
        **base,
        "existing_company": None,
        "new_company": nc,
    }


def parse_http_detail(body: dict[str, Any] | str) -> tuple[str | None, str | None]:
    if not isinstance(body, dict):
        return None, None
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("field"), detail.get("message")
    if isinstance(detail, str):
        return None, detail
    return None, None


def is_email_already_used_400(status_code: int, body: dict[str, Any] | str) -> bool:
    """400 inscription : email deja pris (ne pas confondre avec 'company existe deja')."""
    if status_code != 400:
        return False
    field, message = parse_http_detail(body)
    if field == "email":
        return True
    msg = (message or "").lower()
    return "utilisateur" in msg and "email" in msg and ("deja" in msg or "déjà" in msg)


def is_company_already_exists_on_new_path(status_code: int, body: dict[str, Any] | str) -> bool:
    """new_company refuse car la TVA existe deja : il faut repasser par existing_company."""
    if status_code != 400:
        return False
    field, message = parse_http_detail(body)
    if field == "new_company.tva_intra_com":
        return True
    msg = (message or "").lower()
    return "existe deja" in msg and "existing_company" in msg


def is_company_not_found_for_existing(status_code: int, body: dict[str, Any] | str) -> bool:
    if status_code != 400:
        return False
    field, message = parse_http_detail(body)
    if field == "existing_company.company_id":
        return True
    msg = (message or "").lower()
    blob = json.dumps(body, ensure_ascii=False).lower() if isinstance(body, dict) else str(body).lower()
    return "introuvable" in msg and "company" in msg or "introuvable" in blob and "existing" in blob


def company_email_for_api(raw_email: Any, fallback: str) -> str:
    """
    Email societe dans new_company : EmailStr refuse certains TLD (.test, etc.).
    Si le raw OLD_DATA est douteux, on prend le fallback factice.
    """
    e = compact(raw_email, "")
    if not e or "@" not in e:
        return fallback
    dom = e.rsplit("@", 1)[-1].lower()
    bad = (".test", ".example", ".invalid", ".localhost")
    if dom in ("test", "example", "invalid", "localhost") or any(dom.endswith(s) for s in bad):
        return fallback
    return e[:320]


def post_json(url: str, payload: dict[str, Any], timeout: int) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, body
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def register_with_fallback(
    endpoint: str,
    company: dict[str, Any],
    company_index: int,
    role: str,
    language_id: int,
    timeout: int,
    dry_run: bool,
    email_domain: str,
) -> tuple[str, int | None, dict[str, Any] | str | None]:
    """
    Retourne (statut_resume, status_code_final, body_final)
    statut_resume: ok_existing | ok_new | skip_dup | err
    """
    company_tva = build_company_tva(company, company_index)
    payload_existing = build_payload_existing(
        company, company_index, role, language_id, company_tva, email_domain
    )
    payload_new = build_payload_new(
        company, company_index, role, language_id, company_tva, email_domain
    )

    if dry_run:
        print(
            f"[DRY] {role.upper()} | tva={company_tva} | "
            f"1) existing_company -> 2) new_company si introuvable | email={payload_existing['email']}"
        )
        return "dry", None, None

    status1, body1 = post_json(endpoint, payload_existing, timeout=timeout)
    if status1 in (200, 201):
        return "ok_existing", status1, body1

    if is_company_not_found_for_existing(status1, body1):
        status2, body2 = post_json(endpoint, payload_new, timeout=timeout)
        if status2 in (200, 201):
            return "ok_new", status2, body2
        if is_company_already_exists_on_new_path(status2, body2):
            # Entre-temps la company a ete creee (autre run / course) : rattachement direct
            status3, body3 = post_json(endpoint, payload_existing, timeout=timeout)
            if status3 in (200, 201):
                return "ok_existing", status3, body3
            if is_email_already_used_400(status3, body3):
                return "skip_dup", status3, body3
            return "err", status3, body3
        if is_email_already_used_400(status2, body2):
            return "skip_dup", status2, body2
        return "err", status2, body2

    if is_email_already_used_400(status1, body1):
        return "skip_dup", status1, body1
    return "err", status1, body1


def main() -> None:
    args = parse_args()
    max_attempts = (
        args.max_attempts
        if args.max_attempts is not None
        else max(200, int(args.limit) * 40)
    )
    companies_path = Path(args.companies_raw_path).resolve()
    if not companies_path.exists():
        raise FileNotFoundError(f"companies_raw.json introuvable: {companies_path}")

    companies = json.loads(companies_path.read_text(encoding="utf-8"))
    if not isinstance(companies, list):
        raise ValueError("companies_raw.json doit contenir une liste d'objets")

    role_endpoints = [
        ("supplier", f"{args.base_url.rstrip('/')}/suppliers/v2/register"),
        ("client", f"{args.base_url.rstrip('/')}/clients/v2/register"),
    ]

    created = 0
    ok_existing = 0
    ok_new = 0
    skipped = 0
    failed = 0
    attempted = 0
    used_emails: set[str] = set()

    print(f"[INFO] Source: {companies_path}")
    print(f"[INFO] Lignes source: {len(companies)}")
    print(f"[INFO] Mode dry-run: {args.dry_run}")
    print(f"[INFO] Limite succes: {args.limit}")
    print(f"[INFO] Max tentatives (lignes source): {max_attempts}")
    print(f"[INFO] Domaine email factice: {args.email_domain}")
    print(
        "[INFO] Flux API: 1) existing_company 2) si introuvable -> new_company "
        "3) si 'company existe deja' -> existing_company. "
        "Les logs Uvicorn peuvent montrer un 400 puis un 201 par ligne : c'est normal."
    )

    for idx, company in enumerate(companies, start=1):
        if created >= args.limit:
            break
        if attempted >= max_attempts:
            print(
                f"[WARN] Arret: max-attempts={max_attempts} "
                f"(succes: {created}/{args.limit}). Augmente --max-attempts si besoin."
            )
            break
        if not isinstance(company, dict):
            skipped += 1
            continue

        role, endpoint = role_endpoints[(idx - 1) % 2]
        company_tva = build_company_tva(company, idx)
        email = build_email(company, role, idx, args.email_domain)

        if email in used_emails:
            skipped += 1
            continue
        used_emails.add(email)

        attempted += 1

        outcome, status, body = register_with_fallback(
            endpoint=endpoint,
            company=company,
            company_index=idx,
            role=role,
            language_id=args.language_id,
            timeout=args.timeout,
            dry_run=args.dry_run,
            email_domain=args.email_domain,
        )

        if outcome == "dry":
            created += 1
            continue

        if outcome == "ok_existing":
            created += 1
            ok_existing += 1
            print(f"[OK] {role.upper()} via EXISTING | tva={company_tva} | email={email}")
            continue

        if outcome == "ok_new":
            created += 1
            ok_new += 1
            print(f"[OK] {role.upper()} via NEW_COMPANY | tva={company_tva} | email={email}")
            continue

        if outcome == "skip_dup":
            skipped += 1
            print(f"[SKIP] {role.upper()} conflit / deja present | email={email} | http={status}")
            continue

        failed += 1
        body_text = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
        print(
            f"[ERR] {role.upper()} | email={email} | tva={company_tva} | status={status} | "
            f"body={body_text[:280]}"
        )

    print("\n=== RESULTAT ===")
    print(f"Lignes parcourues (tentatives email) : {attempted}")
    print(f"Profils crees (limite atteinte)     : {created}")
    if not args.dry_run:
        print(f"  dont rattachement company existante: {ok_existing}")
        print(f"  dont creation new_company          : {ok_new}")
    print(f"Skips                                : {skipped}")
    print(f"Erreurs                              : {failed}")
    print(f"Limite succes                        : {args.limit}")


if __name__ == "__main__":
    main()
