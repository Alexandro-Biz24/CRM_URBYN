"""Création d'un devis Sellsy à partir d'une demande Urbyn, puis envoi par email."""

from __future__ import annotations

import json
import logging
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ClientOrder, Company, CompanyUser, Product, ProductTranslation, UserProfile
from app.services.email_sender import EmailDeliveryError, send_html_email
from app.services.entreprise_search import search_french_companies

logger = logging.getLogger(__name__)

_TOKEN = ""
_TOKEN_UNTIL = 0.0
_TAX_ID: int | None = None
_API = "https://api.sellsy.com/v2"
_LOGIN = "https://login.sellsy.com/oauth2/access-tokens"


class SellsyError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@contextmanager
def _ipv4():
    original = socket.getaddrinfo

    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = resolve
    try:
        yield
    finally:
        socket.getaddrinfo = original


def _money(value: float | Decimal | str) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"


def _request(method: str, url: str, body: dict | list | None = None, token: str | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _ipv4():
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SellsyError(detail or f"HTTP {exc.code}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise SellsyError(f"Sellsy injoignable : {exc.reason}") from exc


def _token() -> str:
    global _TOKEN, _TOKEN_UNTIL
    if _TOKEN and time.time() < _TOKEN_UNTIL:
        return _TOKEN
    payload = _request(
        "POST",
        _LOGIN,
        {
            "grant_type": "client_credentials",
            "client_id": settings.SELLSY_CLIENT_ID.strip(),
            "client_secret": settings.SELLSY_CLIENT_SECRET.strip(),
        },
    )
    _TOKEN = str(payload.get("access_token") or "")
    if not _TOKEN:
        raise SellsyError("Jeton Sellsy vide.")
    _TOKEN_UNTIL = time.time() + max(60, int(payload.get("expires_in") or 3600) - 120)
    return _TOKEN


def _api(method: str, path: str, body: dict | list | None = None) -> Any:
    return _request(method, _API + path, body, _token())


def _tax_id() -> int:
    global _TAX_ID
    if _TAX_ID:
        return _TAX_ID
    payload = _api("GET", "/taxes?limit=100")
    rows = payload.get("data") if isinstance(payload, dict) else None
    chosen = None
    for row in rows or []:
        if not row.get("is_active") or row.get("is_ecotax"):
            continue
        rate = str(row.get("rate") or "")
        if rate in {"20", "20.0", "20.00"}:
            chosen = int(row["id"])
            break
    if chosen is None and rows:
        chosen = int(rows[0]["id"])
    if chosen is None:
        raise SellsyError("Aucune taxe Sellsy disponible.")
    _TAX_ID = chosen
    return chosen


def _urbyn(value: str, limit: int) -> str:
    """Préfixe visible Sellsy : URBYN- puis le nom."""
    text = (value or "").strip() or "sans-nom"
    if text.upper().startswith("URBYN-"):
        return text[:limit]
    return f"URBYN-{text}"[:limit]


def _phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if digits.startswith("0") and len(digits) == 10:
        return "+33" + digits[1:]
    return digits or None


def _siren_from_vat(vat: str | None) -> str | None:
    compact = re.sub(r"\s+", "", vat or "").upper()
    match = re.fullmatch(r"FR[0-9A-Z]{2}(\d{9})", compact)
    return match.group(1) if match else None


def _real_company_name(name: str | None) -> str:
    """Nom commercial réel, sans le préfixe URBYN- utilisé pour les articles."""
    text = (name or "").strip()
    if text.upper().startswith("URBYN-"):
        text = text[6:].strip()
    return (text or "Société")[:250]


def _naf_code(raw: str | None) -> str | None:
    code = re.sub(r"[^0-9A-Z]", "", (raw or "").upper())
    if 5 <= len(code) <= 6:
        return code
    return None


def _registry_identity(company: Company) -> tuple[str | None, str | None]:
    """SIRET du siège et code NAF, via l'annuaire public à partir du SIREN, de la TVA ou du nom."""
    siren = _siren_from_vat(company.tva_intra_com)
    vat = re.sub(r"\s+", "", company.tva_intra_com or "").upper()
    query = siren or vat or _real_company_name(company.company_name)
    try:
        with _ipv4():
            found = search_french_companies(query, limit=8)
    except Exception as exc:
        logger.warning("Annuaire entreprises indisponible : %s", exc)
        return None, None
    wanted = _real_company_name(company.company_name).casefold()
    ranked = []
    for row in found:
        if siren and row.siren != siren:
            continue
        siret = "".join(ch for ch in (row.siret or "") if ch.isdigit())
        if len(siret) != 14:
            continue
        same_name = row.company_name.casefold() == wanted
        ranked.append((0 if same_name else 1, siret, _naf_code(row.code_naf)))
    if not ranked:
        return None, None
    ranked.sort()
    return ranked[0][1], ranked[0][2]


def _legal_france(company: Company, siret: str | None, naf: str | None) -> dict[str, str]:
    legal: dict[str, str] = {}
    vat = re.sub(r"\s+", "", company.tva_intra_com or "").upper()
    if 2 <= len(vat) <= 15:
        legal["vat"] = vat
    siren = _siren_from_vat(vat)
    if siren:
        legal["siren"] = siren
    if siret and len(siret) == 14 and siret.isdigit():
        legal["siret"] = siret
    code = _naf_code(company.code_naf) or naf
    if code:
        legal["ape_naf_code"] = code
    return legal


def _company_email(raw: str | None) -> str | None:
    email = (raw or "").strip()
    if "@" not in email or " " in email:
        return None
    return email


def _company_website(raw: str | None) -> str | None:
    site = (raw or "").strip()
    if not site:
        return None
    if not site.lower().startswith(("http://", "https://")):
        site = f"https://{site}"
    return site[:512]


def buyer_company(db: Session, user_id: int, delivery_company_name: str | None) -> Company | None:
    """Société rattachée au compte. Si plusieurs, celle dont le nom correspond à la livraison."""
    rows = db.scalars(
        select(Company)
        .join(CompanyUser, CompanyUser.company_tva_intra_com == Company.tva_intra_com)
        .where(CompanyUser.user_id == user_id)
    ).all()
    if not rows:
        return None
    wanted = (delivery_company_name or "").strip().casefold()
    if wanted:
        for company in rows:
            if company.company_name.strip().casefold() == wanted:
                return company
    return rows[0]


def _search_companies(filters: dict[str, Any]) -> list[dict]:
    found = _api("POST", "/companies/search", {"filters": filters})
    rows = found.get("data") if isinstance(found, dict) else None
    return list(rows or [])


def _row_ids(row: dict) -> tuple[str, str]:
    legal = row.get("legal_france") if isinstance(row.get("legal_france"), dict) else {}
    vat = re.sub(r"\s+", "", str(row.get("vat") or legal.get("vat") or "")).upper()
    siret = "".join(ch for ch in str(row.get("siret") or legal.get("siret") or "") if ch.isdigit())
    return vat, siret


def _same_party(row: dict, *, name: str, vat: str, siret: str | None) -> bool:
    if row.get("type") == "supplier":
        return False
    row_vat, row_siret = _row_ids(row)
    if vat and row_vat and row_vat != vat:
        return False
    if siret and row_siret and row_siret != siret:
        return False
    if vat and row_vat == vat:
        return True
    if siret and row_siret == siret:
        return True
    row_name = _real_company_name(str(row.get("name") or "")).casefold()
    return row_name == name.casefold()


def _existing_prospect(company: Company, siret: str | None) -> dict | None:
    """Fiche Sellsy déjà présente : TVA, SIRET, référence interne, puis nom exact."""
    name = _real_company_name(company.company_name)
    vat = re.sub(r"\s+", "", company.tva_intra_com or "").upper()
    reference = _urbyn(company.tva_intra_com, 100)
    seen: set[int] = set()
    found: list[dict] = []
    searches: list[dict[str, Any]] = [{"reference": [reference]}]
    if vat:
        searches.append({"vat": vat})
    if siret:
        searches.append({"siret": siret})
    searches.append({"name": name})
    for filters in searches:
        try:
            rows = _search_companies(filters)
        except SellsyError as exc:
            logger.warning("Recherche société Sellsy %s : %s", filters, exc)
            continue
        for row in rows:
            row_id = row.get("id")
            if row_id in seen:
                continue
            if not _same_party(row, name=name, vat=vat, siret=siret):
                continue
            seen.add(int(row_id))
            found.append(row)
        if found and "name" not in filters:
            break
    if not found:
        return None
    if len(found) == 1:
        return found[0]
    for row in found:
        row_vat, row_siret = _row_ids(row)
        if (vat and row_vat == vat) or (siret and row_siret == siret):
            return row
    return None


def _find_or_create_prospect(company: Company) -> int:
    """Prospect au nom réel de la société cliente. Réutilise la fiche Sellsy si elle existe."""
    name = _real_company_name(company.company_name)
    reference = _urbyn(company.tva_intra_com, 100)
    siret, registry_naf = _registry_identity(company)
    legal = _legal_france(company, siret, registry_naf)
    existing = _existing_prospect(company, siret)
    body: dict[str, Any] = {"name": name}
    current_ref = str((existing or {}).get("reference") or "").strip()
    if not current_ref or current_ref.upper() == reference.upper():
        body["reference"] = reference
    email = _company_email(company.email)
    phone = _phone(company.phone_number)
    website = _company_website(company.website)
    if email:
        body["email"] = email
    if phone:
        body["phone_number"] = phone
    if website:
        body["website"] = website
    if company.description:
        body["main_activity_description"] = company.description[:2000]
    if legal:
        body["legal_france"] = legal

    if existing:
        company_id = int(existing["id"])
        try:
            _api("PUT", f"/companies/{company_id}", body)
        except SellsyError as exc:
            logger.warning("Mise à jour prospect Sellsy %s : %s", company_id, exc)
        return company_id

    body["type"] = "prospect"
    created = _api("POST", "/companies", body)
    return int(created["id"])


def _person_key(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _contact_matches(row: dict, *, first: str | None, last: str, email: str) -> bool:
    row_email = (row.get("email") or "").strip().casefold()
    if email and row_email == email.casefold():
        return True
    return (
        _person_key(row.get("last_name")) == _person_key(last)
        and _person_key(row.get("first_name")) == _person_key(first)
    )


def _known_contact(company_id: int, *, first: str | None, last: str, email: str) -> int | None:
    """Même intervenant déjà lié à la société, ou déjà connu dans Sellsy par son email."""
    try:
        listed = _api("GET", f"/companies/{company_id}/contacts?limit=100")
    except SellsyError as exc:
        logger.warning("Contacts société Sellsy %s : %s", company_id, exc)
        listed = {}
    rows = listed.get("data") if isinstance(listed, dict) else None
    for row in rows or []:
        if _contact_matches(row, first=first, last=last, email=email):
            return int(row["id"])
    if not email:
        return None
    found = _api("POST", "/contacts/search", {"filters": {"email": email}})
    matches = found.get("data") if isinstance(found, dict) else None
    for row in matches or []:
        if _contact_matches(row, first=first, last=last, email=email):
            return int(row["id"])
    return None


def _civility(title: str | None) -> str | None:
    key = _fold(title).replace(".", "")
    if key in {"m", "mr", "monsieur"}:
        return "mr"
    if key in {"mme", "madame", "mrs"}:
        return "mrs"
    if key in {"mlle", "mademoiselle", "ms"}:
        return "ms"
    return None


def _ensure_main_contact(
    company_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    title: str | None = None,
) -> int | None:
    """Contact principal = la personne. Réutilise l'intervenant déjà présent."""
    last = (last_name or "").strip() or (first_name or "").strip() or "Contact"
    first = (first_name or "").strip() or None
    civility = _civility(title)
    contact_id = _known_contact(company_id, first=first, last=last, email=email)
    if contact_id is None:
        body: dict[str, Any] = {"last_name": last[:200]}
        if first:
            body["first_name"] = first[:200]
        if civility:
            body["civility"] = civility
        if email:
            body["email"] = email
        mobile = _phone(phone)
        if mobile:
            body["mobile_number"] = mobile
        try:
            created = _api("POST", "/contacts", body)
            contact_id = int(created["id"])
        except SellsyError as exc:
            if "email" not in str(exc).lower():
                logger.warning("Contact Sellsy non créé : %s", exc)
                return None
            body.pop("email", None)
            body.pop("mobile_number", None)
            created = _api("POST", "/contacts", body)
            contact_id = int(created["id"])
    elif civility:
        try:
            _api("PUT", f"/contacts/{contact_id}", {"civility": civility})
        except SellsyError as exc:
            logger.warning("Civilité contact Sellsy %s : %s", contact_id, exc)
    try:
        _api(
            "POST",
            f"/companies/{company_id}/contacts/{contact_id}",
            {"roles": ["main"]},
        )
    except SellsyError as exc:
        logger.warning("Lien contact principal Sellsy %s : %s", company_id, exc)
    return contact_id


def _item_id(sku: str, name: str, unit_ht: float) -> tuple[int, str] | None:
    sku = _urbyn(sku, 250)
    name = _urbyn(name, 250)
    try:
        found = _api(
            "POST",
            "/items/search",
            {"filters": {"reference": sku, "type": ["product", "service"]}},
        )
    except SellsyError as exc:
        logger.warning("Recherche article Sellsy %s : %s", sku, exc)
        return None
    rows = found.get("data") if isinstance(found, dict) else None
    if rows:
        kind = rows[0].get("type") if rows[0].get("type") in {"product", "service"} else "service"
        return int(rows[0]["id"]), kind
    try:
        created = _api(
            "POST",
            "/items",
            {
                "type": "service",
                "reference": sku[:250],
                "name": name[:250],
                "reference_price": _money(unit_ht),
                "is_reference_price_taxes_free": True,
            },
        )
    except SellsyError as exc:
        logger.warning("Création article Sellsy %s : %s", sku, exc)
        return None
    item_id = created.get("id") if isinstance(created, dict) else None
    return (int(item_id), "service") if item_id else None


def _single_row(label: str, quantity: float, unit_ht: float, description: str, tax_id: int) -> dict:
    return {
        "type": "single",
        "reference": label[:250],
        "description": description[:2000],
        "quantity": _money(quantity),
        "unit_amount": _money(unit_ht),
        "tax_id": tax_id,
    }


def _catalog_row(
    item_id: int,
    item_type: str,
    label: str,
    quantity: float,
    unit_ht: float,
    description: str,
    tax_id: int,
) -> dict:
    return {
        "type": "catalog",
        "related": {"id": item_id, "type": item_type},
        "reference": label[:250],
        "description": description[:2000],
        "quantity": _money(quantity),
        "unit_amount": _money(unit_ht),
        "tax_id": tax_id,
    }


_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
_PRESTATION = {
    "Massif Béton": "massif béton",
    "Totem": "totem",
    "Palissade": "palissade",
    "Panneau de chantier": "panneau de chantier",
    "Patio": "patio",
    "Facade/Echafaudage": "façade et échafaudage",
    "Installation de chantier": "installation de chantier",
    "Candelize": "candelize",
    "Altize - Caisson Grue": "altize",
    "Modulize - Habillage Module": "modulize",
    "Autre dispositif": "habillage urbain",
}
_COUNTRY_CODES = {
    "france": "FR",
    "fr": "FR",
    "suisse": "CH",
    "switzerland": "CH",
    "ch": "CH",
    "belgique": "BE",
    "belgium": "BE",
    "be": "BE",
    "luxembourg": "LU",
    "lu": "LU",
}


def _french_date(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _prestation_sentence(solutions: list[str], when: date) -> str:
    labels = [_PRESTATION.get(name, name.casefold()) for name in solutions] or ["habillage urbain"]
    parts = []
    for label in labels:
        particle = "d'" if label[:1].lower() in "aeiouéèêàâîôûh" else "de "
        parts.append(f"{particle}{label}")
    if len(parts) == 1:
        joined = parts[0]
    elif len(parts) == 2:
        joined = f"{parts[0]} et {parts[1]}"
    else:
        joined = ", ".join(parts[:-1]) + " et " + parts[-1]
    return (
        "Réalisation d'une prestation "
        f"{joined} décrite depuis les informations communiquées en date du {_french_date(when)}"
    )


def _quote_subject(opportunity: dict) -> str:
    name = str(opportunity.get("name") or "Devis").strip()
    number = str(opportunity.get("number") or "").strip()
    if number and number not in name:
        name = f"{name}-{number}"
    return name[:250]


def _delivery_note(address: dict | None) -> str:
    if not isinstance(address, dict):
        return ""
    lines = ["Adresse de livraison"]
    for key in ("company", "street", "street2"):
        text = str(address.get(key) or "").strip()
        if text:
            lines.append(text)
    city = " ".join(
        part
        for part in (str(address.get("postalCode") or "").strip(), str(address.get("city") or "").strip())
        if part
    )
    if city:
        lines.append(city)
    country = str(address.get("country") or "").strip()
    if country:
        lines.append(country)
    instructions = str(address.get("specialInstructions") or "").strip()
    if instructions:
        lines.extend(["", "Instructions de livraison", instructions])
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _country_code(value: str | None) -> str:
    raw = (value or "").strip()
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    return _COUNTRY_CODES.get(_fold(raw), "FR")


def _ensure_company_address(company_id: int, company: Company, delivery: dict | None) -> None:
    """Adresse de facturation du prospect, pour le bloc société en tête de devis."""
    postal = None
    for address in sorted(
        list(company.addresses or []),
        key=lambda row: (0 if _fold(row.type) in {"headquarter", "siege", "siege social"} or row.is_primary else 1),
    ):
        if (address.street or "").strip() and (address.city or "").strip() and (address.zip_code or "").strip():
            postal = {
                "address_line_1": address.street.strip()[:250],
                "postal_code": address.zip_code.strip()[:30],
                "city": address.city.strip()[:250],
                "country_code": _country_code(address.country_code),
            }
            break
    if postal is None and isinstance(delivery, dict):
        street = str(delivery.get("street") or "").strip()
        city = str(delivery.get("city") or "").strip()
        code = str(delivery.get("postalCode") or "").strip()
        if street and city and code:
            postal = {
                "address_line_1": street[:250],
                "postal_code": code[:30],
                "city": city[:250],
                "country_code": _country_code(str(delivery.get("country") or "")),
            }
            extra = str(delivery.get("street2") or "").strip()
            if extra:
                postal["address_line_2"] = extra[:250]
    if postal is None or len(postal["postal_code"]) < 2 or len(postal["city"]) < 2:
        return
    postal["name"] = "Siège"
    postal["is_invoicing_address"] = True
    try:
        listed = _api("GET", f"/companies/{company_id}/addresses?limit=20")
    except SellsyError as exc:
        logger.warning("Adresses prospect Sellsy %s : %s", company_id, exc)
        return
    rows = listed.get("data") if isinstance(listed, dict) else None
    current = next((row for row in rows or [] if row.get("is_invoicing_address")), None)
    if current is None and rows:
        current = rows[0]
    try:
        if current:
            _api("PUT", f"/companies/{company_id}/addresses/{int(current['id'])}", postal)
        else:
            _api("POST", f"/companies/{company_id}/addresses", postal)
    except SellsyError as exc:
        logger.warning("Adresse prospect Sellsy %s : %s", company_id, exc)


def _euro(value: float) -> str:
    amount = f"{Decimal(str(value)).quantize(Decimal('0.01')):,.2f}"
    return amount.replace(",", " ").replace(".", ",") + " €"


def _payment_footer() -> dict[str, Any]:
    """Validité +21 j, virement, acompte 50 %, solde à 30 jours, TVA sur encaissements."""
    footer: dict[str, Any] = {
        "expiry_date": (date.today() + timedelta(days=21)).isoformat(),
        "vat_mode": "collection",
        "deposit": {"type": "percent", "value": "50.00"},
        "company_reference": "",
        "bank_account_id": 267590,
    }
    try:
        methods = _api("GET", "/payments/methods?limit=100")
        for row in methods.get("data") or []:
            if _fold(str(row.get("label") or "")) == "virement bancaire":
                footer["payment_method_ids"] = [int(row["id"])]
                break
    except SellsyError as exc:
        logger.warning("Moyens de règlement Sellsy : %s", exc)
    try:
        terms = _api("GET", "/payment-terms?limit=100")
        for row in terms.get("data") or []:
            if str(row.get("code") or "") == "30days" and "30" in _fold(str(row.get("label") or "")):
                footer["payment_terms"] = {
                    "id": int(row["id"]),
                    "code": "30days",
                    "end_of_month": False,
                }
                break
    except SellsyError as exc:
        logger.warning("Conditions de règlement Sellsy : %s", exc)
    try:
        banks = _api("GET", "/bank-accounts?limit=20")
        rows = banks.get("data") or []
        if rows:
            footer["bank_account_id"] = int(rows[0]["id"])
    except SellsyError as exc:
        logger.warning("Compte bancaire Sellsy : le devis reprend le compte déjà utilisé. %s", exc)
    return footer


def _shipping_item_id() -> int | None:
    try:
        found = _api("POST", "/items/search", {"filters": {"type": ["shipping"], "name": "Frais de port"}})
    except SellsyError as exc:
        logger.warning("Recherche frais de port Sellsy : %s", exc)
        return None
    rows = found.get("data") if isinstance(found, dict) else None
    for row in rows or []:
        if _fold(str(row.get("name") or "")) == "frais de port":
            return int(row["id"])
    if rows:
        return int(rows[0]["id"])
    try:
        created = _api(
            "POST",
            "/items",
            {"type": "shipping", "name": "Frais de port", "reference": "FRAIS-PORT"},
        )
    except SellsyError as exc:
        logger.warning("Création frais de port Sellsy : %s", exc)
        return None
    item_id = created.get("id") if isinstance(created, dict) else None
    return int(item_id) if item_id else None


def _shipping_row(amount: float, tax_id: int) -> dict:
    item_id = _shipping_item_id()
    if item_id:
        return {
            "type": "shipping",
            "related": {"id": item_id, "type": "shipping"},
            "quantity": "1.00",
            "unit_amount": _money(amount),
            "tax_id": tax_id,
        }
    return _single_row("Frais de port", 1, amount, "Frais de port", tax_id)


def _delivery_text(address: dict | None) -> str:
    if not isinstance(address, dict):
        return ""
    parts = [
        address.get("company"),
        address.get("street"),
        address.get("street2"),
        " ".join(
            p
            for p in (str(address.get("postalCode") or ""), str(address.get("city") or ""))
            if p.strip()
        ),
        address.get("country"),
    ]
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def issue_estimate(
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    company_id: int,
    contact_id: int | None,
    opportunity_id: int,
    staff_id: int | None,
    subject: str,
    note: str,
    intro: str,
    product_rows: list[dict[str, Any]],
    install_rows: list[tuple[str, float]],
    shipping_ht: float = 0,
    discount_ht: float = 0,
) -> dict[str, Any]:
    """Devis lié au prospect et à l'opportunité déjà créés, puis envoi de l'email."""
    if not settings.SELLSY_CLIENT_ID.strip() or not settings.SELLSY_CLIENT_SECRET.strip():
        return {
            "email_sent": False,
            "message": "Sellsy n'est pas configuré.",
        }

    tax_id = _tax_id()
    rows: list[dict] = [{"type": "comment", "text": intro[:4000]}]
    material: list[dict] = []
    for row in product_rows:
        raw_label = str(row["label"])
        label = _urbyn(raw_label, 250)
        qty = float(row["quantity"])
        unit = float(row["unit_ht"])
        description = str(row.get("description") or raw_label)[:2000]
        sku = _urbyn((row.get("sku") or raw_label).strip(), 250)
        linked = _item_id(sku, label, unit)
        if linked:
            item_id, item_type = linked
            material.append(_catalog_row(item_id, item_type, sku, qty, unit, description, tax_id))
        else:
            material.append(_single_row(label, qty, unit, description, tax_id))
    material_ht = round(sum(float(row["unit_ht"]) * float(row["quantity"]) for row in product_rows), 2)
    service_ht = round(sum(amount for _, amount in install_rows if amount > 0), 2)
    if material:
        rows.append({"type": "title", "text": "I/ MATÉRIEL"})
        rows.extend(material)
        rows.append({"type": "sub-total"})
    installation = [
        _single_row(label, 1, amount, label, tax_id)
        for label, amount in install_rows
        if amount > 0
    ]
    if installation:
        rows.append({"type": "title", "text": "II/ SERVICE"})
        rows.extend(installation)
        rows.append({"type": "sub-total"})
    if shipping_ht > 0:
        rows.append({"type": "title", "text": "III/ LIVRAISON"})
        rows.append(_shipping_row(shipping_ht, tax_id))
        rows.append({"type": "sub-total"})
    rows.append(
        {
            "type": "comment",
            "text": (
                f"Sous-total matériel : {_euro(material_ht)}\n"
                f"Sous-total service : {_euro(service_ht)}\n"
                f"Frais de port : {_euro(shipping_ht)}"
            ),
        }
    )
    if len(rows) == 2:
        raise SellsyError("Le devis n'a aucune ligne.")

    payload: dict[str, Any] = {
        "date": date.today().isoformat(),
        "subject": subject[:250],
        "related": [
            {"type": "company", "id": company_id},
            {"type": "opportunity", "id": opportunity_id},
        ],
        "currency": "EUR",
        "note": note[:4000],
        "public_link_enabled": True,
        "rows": rows,
    }
    if contact_id:
        payload["contact_id"] = contact_id
    if staff_id:
        payload["assigned_staff_id"] = staff_id
        payload["owner_id"] = staff_id
    payload.update(_payment_footer())
    payload["settings"] = {
        "pdf_display": {
            "show_contact_name": True,
            "show_vat_number": True,
            "show_company_reference": False,
            "show_delivery_address": False,
            "show_bank_account": True,
            "show_payment_methods": True,
            "show_payment_terms": True,
        }
    }
    if discount_ht > 0:
        payload["discount"] = {"type": "amount", "value": _money(discount_ht)}

    created = _create_estimate(payload)
    estimate_id = int(created["id"])
    number = str(created.get("number") or "")
    pdf_link = str(created.get("pdf_link") or "")
    public_link = created.get("public_link")
    pdf = None
    for attempt in range(8):
        if attempt:
            time.sleep(1.5)
            fresh = _api("GET", f"/estimates/{estimate_id}")
            pdf_link = str(fresh.get("pdf_link") or pdf_link)
            public_link = fresh.get("public_link") or public_link
        pdf = _pdf_bytes(pdf_link)
        if pdf:
            break

    signature_url, signature_started = _enable_signature(
        estimate_id,
        contact_id=contact_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
    )
    email_sent, channel, message = _send_estimate_email(
        estimate_id=estimate_id,
        number=number,
        first_name=first_name,
        email=email,
        pdf=pdf,
        pay_url=str(public_link or ""),
        signature_url=signature_url,
        signature_started=signature_started,
    )
    if email_sent:
        try:
            _api("PUT", f"/estimates/{estimate_id}/status", {"status": "sent"})
        except SellsyError as exc:
            logger.warning("Statut devis Sellsy %s : %s", estimate_id, exc)
        _move_to_devis_froid(opportunity_id)

    return {
        "estimate_id": estimate_id,
        "number": number,
        "pdf_link": pdf_link,
        "public_link": public_link,
        "signature_url": signature_url,
        "company_id": company_id,
        "contact_id": contact_id,
        "opportunity_id": opportunity_id,
        "email_sent": email_sent,
        "email_channel": channel,
        "message": message,
    }


def _download(url: str) -> bytes:
    def fetch(with_token: bool) -> bytes:
        headers = {"Accept": "application/pdf"}
        if with_token:
            headers["Authorization"] = f"Bearer {_token()}"
        req = urllib.request.Request(url, headers=headers)
        with _ipv4():
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()

    try:
        return fetch(False)
    except urllib.error.HTTPError:
        return fetch(True)


def _pdf_bytes(url: str) -> bytes | None:
    if not url:
        return None
    try:
        data = _download(url)
    except (urllib.error.URLError, TimeoutError, SellsyError) as exc:
        logger.warning("PDF du devis inaccessible : %s", exc)
        return None
    if data.startswith(b"%PDF"):
        return data
    logger.warning("Le lien PDF Sellsy n'a pas renvoyé un PDF (%s octets).", len(data))
    return None


_PAYMENT_MODULES = ("stripe", "stancer", "paypal", "adyen", "atos")


def _create_estimate(payload: dict[str, Any]) -> dict:
    """Active le paiement en ligne si un module du compte l'accepte."""
    settings_body = dict(payload.get("settings") or {})
    for module in _PAYMENT_MODULES:
        attempt = dict(payload)
        attempt["settings"] = {
            **settings_body,
            "payments": {"payment_modules": [module], "direct_debit_module": None},
        }
        try:
            return _api("POST", "/estimates", attempt)
        except SellsyError as exc:
            text = str(exc).lower()
            if module in text or "payment" in text or "direct_debit" in text:
                logger.warning("Paiement en ligne %s indisponible : %s", module, exc)
                continue
            raise
    return _api("POST", "/estimates", payload)


def _enable_signature(
    estimate_id: int,
    *,
    contact_id: int | None,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
) -> tuple[str | None, bool]:
    """Ouvre la signature électronique. Sellsy peut aussi envoyer son propre email au signataire."""
    if not contact_id:
        logger.warning("Signature électronique ignorée : devis %s sans contact.", estimate_id)
        return None, False
    signer: dict[str, Any] = {
        "type": "contact",
        "id": contact_id,
        "last_name": (last_name or first_name or "Contact")[:200],
        "email": email,
    }
    if first_name.strip():
        signer["first_name"] = first_name.strip()[:200]
    mobile = _phone(phone)
    if mobile:
        signer["phone_number"] = mobile
    try:
        created = _api(
            "POST",
            f"/estimates/{estimate_id}/esign",
            {"auth_mode": "email", "related": [signer]},
        )
    except SellsyError as exc:
        logger.warning("Signature électronique devis %s : %s", estimate_id, exc)
        return None, False
    cosigners = created.get("cosigners") if isinstance(created, dict) else None
    if not cosigners:
        return None, True
    signer_row = cosigners[0]
    url = str(signer_row.get("public_link") or signer_row.get("signature_url") or "") or None
    return url, True


def _send_estimate_email(
    *,
    estimate_id: int,
    number: str,
    first_name: str,
    email: str,
    pdf: bytes | None,
    pay_url: str,
    signature_url: str | None,
    signature_started: bool,
) -> tuple[bool, str | None, str]:
    greeting = first_name.strip() or "Bonjour"
    label = number or str(estimate_id)
    filename = f"devis-{label}.pdf"
    pay_text = f"Payer le devis : {pay_url}\n" if pay_url else ""
    if signature_url:
        sign_text = f"Signer électroniquement le devis : {signature_url}\n"
    elif signature_started:
        sign_text = "La demande de signature électronique part dans un email séparé.\n"
    else:
        sign_text = ""
    text = (
        f"Bonjour {greeting},\n\n"
        f"Votre devis Urbyn {label} est en pièce jointe.\n"
        f"{pay_text}{sign_text}\n"
        "L'équipe Urbanize"
    )
    pay_html = (
        f'<p><a href="{pay_url}">Payer le devis</a></p>' if pay_url else ""
    )
    if signature_url:
        sign_html = f'<p><a href="{signature_url}">Signer électroniquement le devis</a></p>'
    elif signature_started:
        sign_html = "<p>La demande de signature électronique part dans un email séparé.</p>"
    else:
        sign_html = ""
    html = (
        f"<p>Bonjour {greeting},</p>"
        f"<p>Votre devis Urbyn <strong>{label}</strong> est en pièce jointe.</p>"
        f"{pay_html}{sign_html}"
        "<p>L'équipe Urbanize</p>"
    )
    if not pdf:
        return (
            False,
            None,
            f"Le devis {label} est créé dans Sellsy. Le PDF n'a pas pu être joint à l'email.",
        )
    try:
        send_html_email(
            to_email=email,
            subject=f"Votre devis Urbyn {label}",
            html=html,
            text=text,
            attachments=[(filename, pdf)],
        )
        return True, "resend", f"Devis {label} envoyé en pièce jointe à {email}."
    except EmailDeliveryError as mail_exc:
        return (
            False,
            None,
            f"Le devis {label} est créé dans Sellsy. L'email n'est pas parti : {mail_exc}",
        )


def _fold(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().replace("/", " ").replace("_", " ").replace("-", " ").split())


def _name_token(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text.upper()


_SOLUTION_ORDER = (
    "Massif Béton",
    "Totem",
    "Palissade",
    "Panneau de chantier",
    "Patio",
    "Facade/Echafaudage",
    "Installation de chantier",
    "Candelize",
    "Altize - Caisson Grue",
    "Modulize - Habillage Module",
    "Autre dispositif",
)
_SOLUTION_ALIASES = {
    "Massif Béton": ("massif beton", "massif", "lestage", "manille", "palette"),
    "Totem": ("totem", "balast", "ballast"),
    "Palissade": ("palissade", "cloture"),
    "Panneau de chantier": ("panneau de chantier", "panneau chantier"),
    "Patio": ("patio", "ombrage"),
    "Facade/Echafaudage": ("facade echafaudage", "facade", "echafaudage"),
    "Installation de chantier": ("installation de chantier",),
    "Candelize": ("candelize",),
    "Altize - Caisson Grue": ("altize", "caisson grue"),
    "Modulize - Habillage Module": ("modulize", "habillage module"),
    "Autre dispositif": ("autre dispositif", "poteau", "store"),
}
_ACCESSORIES = {"palette", "manille", "panels", "balast", "ballast", "installation"}


def _zone_code(country: str | None, postal: str | None) -> str:
    """Département français, ou CH / BE / LU pour la Suisse, la Belgique et le Luxembourg."""
    abroad = {
        "suisse": "CH",
        "switzerland": "CH",
        "ch": "CH",
        "belgique": "BE",
        "belgium": "BE",
        "be": "BE",
        "luxembourg": "LU",
        "lu": "LU",
    }
    key = _fold(country)
    if key in abroad:
        return abroad[key]
    digits = "".join(ch for ch in (postal or "") if ch.isdigit())
    if digits.startswith(("971", "972", "973", "974", "976")):
        return digits[:3]
    if digits.startswith("20") and len(digits) >= 3:
        return "2A" if int(digits[:5] if len(digits) >= 5 else digits) < 20200 else "2B"
    if len(digits) >= 2:
        return digits[:2]
    return "XX"


def _solution_of(item, paths: list[list[str]]) -> str | None:
    kind = _fold(item.item_type)
    if kind in {"palette", "manille"}:
        return "Massif Béton"
    if kind in {"panels", "balast", "ballast"}:
        return "Totem"
    details = item.details if isinstance(item.details, dict) else {}
    text = _fold(
        " ".join(
            [
                kind,
                str(details.get("family") or ""),
                str(details.get("catalogName") or ""),
                item.name or "",
                " ".join(part for path in paths for part in path),
            ]
        )
    )
    for label in _SOLUTION_ORDER:
        if any(alias in text for alias in _SOLUTION_ALIASES[label]):
            return label
    return None


def _line_is_rental(item, paths: list[list[str]]) -> bool:
    details = item.details if isinstance(item.details, dict) else {}
    mode = _fold(str(details.get("mode") or ""))
    if mode in {"location", "loc"}:
        return True
    if mode in {"acquisition", "achat", "aquisition"}:
        return False
    text = _fold(
        " ".join(
            [
                str(details.get("catalogName") or ""),
                " ".join(part for path in paths for part in path),
            ]
        )
    )
    has_rent = "location" in text
    has_buy = "acquisition" in text or "achat" in text or "aquisition" in text
    return has_rent and not has_buy


def _cart_context(db: Session, order: ClientOrder) -> tuple[list[str], str]:
    """Solutions cochées, et Formule Achat dès qu'une ligne du panier n'est pas une location."""
    from app.services.pricing import _product_paths

    solutions: list[str] = []
    rentals: list[bool] = []
    for item in order.items:
        paths = _product_paths(db, item.product_id) if item.product_id else []
        label = _solution_of(item, paths)
        if label and label not in solutions:
            solutions.append(label)
        if _fold(item.item_type) not in _ACCESSORIES:
            rentals.append(_line_is_rental(item, paths))
    ordered = [label for label in _SOLUTION_ORDER if label in solutions]
    formule = "Location" if rentals and all(rentals) else "Achat"
    return ordered, formule


def _opportunity_name(order: ClientOrder, company: Company, solutions: list[str]) -> str:
    address = order.delivery_address if isinstance(order.delivery_address, dict) else {}
    zone = _zone_code(address.get("country"), address.get("postalCode"))
    client = _name_token(_real_company_name(company.company_name)) or "CLIENT"
    city = _name_token(str(address.get("city") or "")) or "VILLE"
    keyword = "+".join(_name_token(label) for label in solutions) or "PROJET"
    period = date.today().strftime("%Y%m")
    return f"{zone}-{client}-{city}-{keyword}-{period}"[:250]


def _list_pages(path: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while offset < 500:
        sep = "&" if "?" in path else "?"
        payload = _api("GET", f"{path}{sep}limit=100&offset={offset}")
        data = payload.get("data") if isinstance(payload, dict) else None
        batch = list(data or [])
        rows.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return rows


def _match_label(choices: list[tuple[int, str]], needles: list[str]) -> int | None:
    folded = [(_fold(label), choice_id) for choice_id, label in choices]
    for needle in needles:
        wanted = _fold(needle)
        for label, choice_id in folded:
            if label == wanted:
                return choice_id
    for needle in needles:
        wanted = _fold(needle)
        if len(wanted) < 4:
            continue
        for label, choice_id in folded:
            if wanted in label or label in wanted:
                return choice_id
    return None


def _choice_ids(choices: list[tuple[int, str]], solutions: list[str]) -> list[int]:
    found: list[int] = []
    for choice_id, label in choices:
        folded = _fold(label)
        for solution in solutions:
            aliases = _SOLUTION_ALIASES.get(solution, (_fold(solution),))
            if any(alias == folded or (len(alias) > 4 and (alias in folded or folded in alias)) for alias in aliases):
                found.append(choice_id)
                break
    return found


def _field_choices(field: dict) -> list[tuple[int, str]]:
    params = field.get("parameters") if isinstance(field.get("parameters"), dict) else {}
    items = params.get("items") if isinstance(params, dict) else None
    choices = []
    for item in items or []:
        if isinstance(item, dict) and item.get("id"):
            choices.append((int(item["id"]), str(item.get("label") or "")))
    return choices


def _custom_values(fields: list[dict], solutions: list[str], formule: str) -> list[dict]:
    values: list[dict] = []
    formule_needles = ["location"] if formule == "Location" else ["achat", "acquisition"]
    service_needles = [alias for solution in solutions for alias in _SOLUTION_ALIASES.get(solution, ())] 
    service_needles.extend(formule_needles)
    for field in fields:
        name = _fold(str(field.get("name") or ""))
        kind = str(field.get("type") or "")
        choices = _field_choices(field)
        if "solution" in name and "service" not in name:
            picked = _choice_ids(choices, solutions)
            if picked and kind == "checkbox":
                values.append({"id": int(field["id"]), "value": picked})
            elif picked:
                values.append({"id": int(field["id"]), "value": picked[0]})
            continue
        if name.startswith("formule") or name == "formule":
            choice = _match_label(choices, formule_needles)
            if choice is not None:
                values.append({"id": int(field["id"]), "value": choice})
            continue
        if "service propose" in name:
            choice = _match_label(choices, service_needles)
            if choice is not None:
                values.append({"id": int(field["id"]), "value": choice})
    return values


def _create_opportunity(
    db: Session,
    order: ClientOrder,
    company: Company,
    *,
    company_id: int,
    contact_id: int | None,
) -> dict[str, Any]:
    """Opportunité ouverte sur le prospect, avant le devis."""
    solutions, formule = _cart_context(db, order)
    name = _opportunity_name(order, company, solutions)
    pipelines = _list_pages("/opportunities/pipelines")
    pipeline = next((row for row in pipelines if _fold(str(row.get("name") or "")).startswith("commercial")), None)
    if pipeline is None:
        raise SellsyError("Pipeline Commercial introuvable dans Sellsy.")
    steps = _list_pages(f"/opportunities/pipelines/{int(pipeline['id'])}/steps")
    step = next(
        (
            row
            for row in steps
            if "qualif" in _fold(str(row.get("name") or ""))
            and str(row.get("name") or "").strip()[:1] == "2"
        ),
        None,
    )
    if step is None:
        step = next((row for row in steps if "qualif" in _fold(str(row.get("name") or ""))), None)
    if step is None:
        raise SellsyError("Étape « 2- qualifié » introuvable dans le pipeline Commercial.")

    source_id = None
    for row in _list_pages("/opportunities/sources"):
        if _fold(str(row.get("name") or "")) == "urbyn":
            source_id = int(row["id"])
            break

    staff_id = None
    try:
        for row in _list_pages("/staffs"):
            first = _fold(str(row.get("first_name") or row.get("firstname") or ""))
            last = _fold(str(row.get("last_name") or row.get("lastname") or ""))
            if last == "rein" and first.startswith("stephane"):
                staff_id = int(row["id"])
                break
    except SellsyError as exc:
        logger.warning("Collaborateur Sellsy illisible : %s", exc)

    related: list[dict[str, Any]] = [{"type": "company", "id": company_id}]
    if contact_id:
        related.append({"type": "contact", "id": contact_id})
    payload: dict[str, Any] = {
        "name": name,
        "status": "open",
        "pipeline": int(pipeline["id"]),
        "step": int(step["id"]),
        "amount": _money(order.total_ht or 0),
        "due_date": (date.today() + timedelta(days=21)).isoformat(),
        "related": related,
        "note": f"Demande Urbyn n°{order.id}. Formule {formule}."[:5000],
    }
    if source_id:
        payload["source"] = source_id
    if staff_id:
        payload["owner_id"] = staff_id
        payload["assigned_staff_ids"] = [staff_id]

    created = _api("POST", "/opportunities", payload)
    opportunity_id = int(created["id"])
    warnings: list[str] = []
    if source_id is None:
        warnings.append("La source Urbyn n'existe pas dans Sellsy.")
    if staff_id is None:
        warnings.append("Stéphane REIN n'a pas été trouvé parmi les collaborateurs.")
    try:
        fields = _api(
            "POST",
            "/custom-fields/search?limit=100",
            {"filters": {"related_object": "opportunity"}},
        )
        values = _custom_values(list(fields.get("data") or []), solutions, formule)
        if values:
            _api("PUT", f"/opportunities/{opportunity_id}/custom-fields", values)
        else:
            warnings.append("Les champs Solution, Service proposé et Formule n'ont pas été reconnus.")
    except SellsyError as exc:
        warnings.append(f"Champs personnalisés non enregistrés : {exc}")
        logger.warning("Champs opportunité Sellsy %s : %s", opportunity_id, exc)

    return {
        "id": opportunity_id,
        "number": created.get("number"),
        "name": name,
        "formule": formule,
        "solutions": solutions,
        "staff_id": staff_id,
        "message": " ".join(warnings),
    }


def _scope_message(exc: SellsyError) -> str:
    text = str(exc)
    if any(scope in text for scope in ("opportunities.", "custom-fields.", "staffs.")):
        return (
            "droits API manquants sur Urbanize_Devis : "
            "opportunities.read, opportunities.write, custom-fields.read, "
            "custom-fields.write, staffs.read."
        )
    return text


def _move_to_devis_froid(opportunity_id: int) -> None:
    """Une fois le devis envoyé, l'opportunité quitte « Qualifié » pour « Devis froid »."""
    try:
        pipelines = _list_pages("/opportunities/pipelines")
        pipeline = next(
            (row for row in pipelines if _fold(str(row.get("name") or "")).startswith("commercial")),
            None,
        )
        if pipeline is None:
            raise SellsyError("Pipeline Commercial introuvable.")
        steps = _list_pages(f"/opportunities/pipelines/{int(pipeline['id'])}/steps")
        step = next((row for row in steps if "devis froid" in _fold(str(row.get("name") or ""))), None)
        if step is None:
            raise SellsyError("Étape « Devis froid » introuvable.")
        _api("PATCH", f"/opportunities/{opportunity_id}/step-rank", {"step": int(step["id"])})
    except SellsyError as exc:
        logger.warning("Étape opportunité %s non passée en devis froid : %s", opportunity_id, exc)


def _bind_estimate(opportunity_id: int, estimate_id: int, number: str, order_id: int) -> None:
    """Le devis devient le document principal de l'opportunité."""
    try:
        _api(
            "PATCH",
            f"/opportunities/{opportunity_id}",
            {
                "main_doc_id": estimate_id,
                "note": f"Demande Urbyn n°{order_id}. Devis {number}.",
            },
        )
    except SellsyError as exc:
        logger.warning("Lien devis %s vers opportunité %s : %s", estimate_id, opportunity_id, exc)


def attach_sellsy_estimate(db: Session, order: ClientOrder) -> None:
    email = (order.contact_email or "").strip()
    if not email:
        return
    product_ids = [it.product_id for it in order.items if it.product_id]
    skus: dict[int, str] = {}
    descriptions: dict[int, str] = {}
    if product_ids:
        products = db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
        skus = {p.id: (p.client_sku or "").strip() for p in products}
        for product_id, text in db.execute(
            select(ProductTranslation.product_id, ProductTranslation.description).where(
                ProductTranslation.product_id.in_(product_ids)
            )
        ):
            cleaned = (text or "").strip()
            if cleaned and product_id not in descriptions:
                descriptions[product_id] = cleaned

    address = order.delivery_address if isinstance(order.delivery_address, dict) else None
    product_rows = []
    for item in order.items:
        sku = skus.get(item.product_id or -1, "")
        details = item.details if isinstance(item.details, dict) else {}
        description = str(details.get("description") or descriptions.get(item.product_id or -1) or item.name)
        product_rows.append(
            {
                "label": item.name,
                "description": description.strip(),
                "quantity": int(item.quantity),
                "unit_ht": float(item.unit_price_ht),
                "sku": sku,
            }
        )
    breakdown = order.shipping_breakdown if isinstance(order.shipping_breakdown, dict) else {}
    install_rows: list[tuple[str, float]] = []
    for key, label in (
        ("dechargement", "Déchargement"),
        ("installation", "Installation"),
        ("totem_installation", "Installation totem"),
    ):
        amount = float(breakdown.get(key) or 0)
        if amount > 0:
            install_rows.append((label, amount))
    shipping_ht = float(order.shipping_amount or 0)

    company = buyer_company(
        db,
        order.buyer_user_id,
        (address or {}).get("company") if isinstance(address, dict) else None,
    )
    if company is None:
        result = {
            "email_sent": False,
            "message": "Devis Sellsy non créé : aucune entreprise n'est rattachée à ce compte.",
        }
        stored = dict(breakdown)
        stored["sellsy"] = result
        order.shipping_breakdown = stored
        db.commit()
        return

    try:
        company_id = _find_or_create_prospect(company)
        profile = db.scalar(select(UserProfile).where(UserProfile.user_id == order.buyer_user_id))
        contact_id = _ensure_main_contact(
            company_id,
            first_name=order.contact_first_name or "",
            last_name=order.contact_last_name or "",
            email=email,
            phone=order.contact_phone,
            title=profile.title if profile else None,
        )
        _ensure_company_address(company_id, company, address)
    except SellsyError as exc:
        result = {"email_sent": False, "message": f"Prospect Sellsy non créé : {exc}"}
        logger.warning("Prospect Sellsy commande %s : %s", order.id, exc)
        stored = dict(breakdown)
        stored["sellsy"] = result
        order.shipping_breakdown = stored
        db.commit()
        return

    try:
        opportunity = _create_opportunity(
            db,
            order,
            company,
            company_id=company_id,
            contact_id=contact_id,
        )
    except SellsyError as exc:
        result = {
            "email_sent": False,
            "company_id": company_id,
            "contact_id": contact_id,
            "message": f"Devis non créé : l'opportunité a échoué. {_scope_message(exc)}",
            "opportunity": {"message": _scope_message(exc)},
        }
        logger.warning("Opportunité Sellsy commande %s : %s", order.id, exc)
        stored = dict(breakdown)
        stored["sellsy"] = result
        order.shipping_breakdown = stored
        db.commit()
        return

    try:
        result = issue_estimate(
            first_name=order.contact_first_name or "",
            last_name=order.contact_last_name or "",
            email=email,
            phone=order.contact_phone,
            company_id=company_id,
            contact_id=contact_id,
            opportunity_id=int(opportunity["id"]),
            staff_id=opportunity.get("staff_id"),
            subject=_quote_subject(opportunity),
            note=_delivery_note(address),
            intro=_prestation_sentence(list(opportunity.get("solutions") or []), date.today()),
            product_rows=product_rows,
            install_rows=install_rows,
            shipping_ht=shipping_ht,
            discount_ht=float(breakdown.get("discount") or 0),
        )
    except SellsyError as exc:
        result = {
            "email_sent": False,
            "company_id": company_id,
            "contact_id": contact_id,
            "opportunity": opportunity,
            "message": f"Prospect et opportunité créés. Devis non créé : {exc}",
        }
        logger.warning("Devis Sellsy commande %s : %s", order.id, exc)
    else:
        if result.get("estimate_id"):
            _bind_estimate(int(opportunity["id"]), int(result["estimate_id"]), str(result.get("number") or ""), order.id)
        result = {**result, "opportunity": opportunity}

    stored = dict(breakdown)
    stored["sellsy"] = result
    order.shipping_breakdown = stored
    db.commit()
