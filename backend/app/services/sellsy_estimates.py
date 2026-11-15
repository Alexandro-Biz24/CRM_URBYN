"""Création d'un devis Sellsy à partir d'une demande Urbyn, puis envoi par email."""

from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ClientOrder, Product
from app.services.email_sender import EmailDeliveryError, send_html_email

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


def _request(method: str, url: str, body: dict | None = None, token: str | None = None) -> Any:
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


def _api(method: str, path: str, body: dict | None = None) -> Any:
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


def _find_or_create_individual(
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    reference: str,
) -> int:
    visible = _urbyn(f"{first_name} {last_name}".strip() or last_name or "Client", 200)
    ref = _urbyn(reference, 100)
    by_ref = _api(
        "POST",
        "/individuals/search",
        {"filters": {"reference": [ref]}},
    )
    ref_rows = by_ref.get("data") if isinstance(by_ref, dict) else None
    if ref_rows:
        return int(ref_rows[0]["id"])
    found = _api("POST", "/individuals/search", {"filters": {"email": email}})
    rows = found.get("data") if isinstance(found, dict) else None
    if rows:
        return int(rows[0]["id"])
    body: dict[str, Any] = {
        "type": "client",
        "last_name": visible,
        "first_name": None,
        "email": email,
        "reference": ref,
    }
    mobile = _phone(phone)
    if mobile:
        body["mobile_number"] = mobile
    try:
        created = _api("POST", "/individuals", body)
    except SellsyError as exc:
        again = _api("POST", "/individuals/search", {"filters": {"email": email}})
        again_rows = again.get("data") if isinstance(again, dict) else None
        if again_rows:
            return int(again_rows[0]["id"])
        # L'adresse d'un collaborateur Sellsy ne peut pas être celle d'un particulier.
        # On crée la fiche sans email : l'envoi du devis utilise quand même l'adresse saisie.
        if "email" in str(exc).lower():
            body.pop("email", None)
            body.pop("mobile_number", None)
            created = _api("POST", "/individuals", body)
        else:
            body.pop("mobile_number", None)
            created = _api("POST", "/individuals", body)
    return int(created["id"])


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
    client_reference: str,
    subject: str,
    note: str,
    product_rows: list[dict[str, Any]],
    fee_rows: list[tuple[str, float, str]],
    discount_ht: float = 0,
) -> dict[str, Any]:
    """Crée le particulier, le devis (produits + frais) et envoie l'email."""
    if not settings.SELLSY_CLIENT_ID.strip() or not settings.SELLSY_CLIENT_SECRET.strip():
        return {
            "email_sent": False,
            "message": "Sellsy n'est pas configuré.",
        }

    tax_id = _tax_id()
    individual_id = _find_or_create_individual(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        reference=client_reference,
    )
    rows: list[dict] = []
    for row in product_rows:
        raw_label = str(row["label"])
        label = _urbyn(raw_label, 250)
        qty = float(row["quantity"])
        unit = float(row["unit_ht"])
        description = str(row.get("description") or raw_label)
        sku = _urbyn((row.get("sku") or raw_label).strip(), 250)
        linked = _item_id(sku, label, unit)
        if linked:
            item_id, item_type = linked
            rows.append(_catalog_row(item_id, item_type, sku, qty, unit, description, tax_id))
        else:
            rows.append(_single_row(label, qty, unit, description, tax_id))
    for label, amount, description in fee_rows:
        if amount > 0:
            rows.append(_single_row(label, 1, amount, description, tax_id))
    if not rows:
        raise SellsyError("Le devis n'a aucune ligne.")

    payload: dict[str, Any] = {
        "date": date.today().isoformat(),
        "subject": _urbyn(subject, 250),
        "related": [{"type": "individual", "id": individual_id}],
        "currency": "EUR",
        "note": note[:4000],
        "public_link_enabled": True,
        "rows": rows,
    }
    if discount_ht > 0:
        payload["discount"] = {"type": "amount", "value": _money(discount_ht)}

    created = _api("POST", "/estimates", payload)
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

    email_sent, channel, message = _send_estimate_email(
        estimate_id=estimate_id,
        number=number,
        first_name=first_name,
        email=email,
        pdf=pdf,
    )
    if email_sent:
        try:
            _api("PUT", f"/estimates/{estimate_id}/status", {"status": "sent"})
        except SellsyError as exc:
            logger.warning("Statut devis Sellsy %s : %s", estimate_id, exc)

    return {
        "estimate_id": estimate_id,
        "number": number,
        "pdf_link": pdf_link,
        "public_link": public_link,
        "individual_id": individual_id,
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


def _send_estimate_email(
    *,
    estimate_id: int,
    number: str,
    first_name: str,
    email: str,
    pdf: bytes | None,
) -> tuple[bool, str | None, str]:
    greeting = first_name.strip() or "Bonjour"
    label = number or str(estimate_id)
    filename = f"devis-{label}.pdf"
    text = (
        f"Bonjour {greeting},\n\n"
        f"Votre devis Urbyn {label} est en pièce jointe.\n\n"
        "L'équipe Urbanize"
    )
    html = (
        f"<p>Bonjour {greeting},</p>"
        f"<p>Votre devis Urbyn <strong>{label}</strong> est en pièce jointe.</p>"
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


def attach_sellsy_estimate(db: Session, order: ClientOrder) -> None:
    email = (order.contact_email or "").strip()
    if not email:
        return
    product_ids = [it.product_id for it in order.items if it.product_id]
    skus: dict[int, str] = {}
    if product_ids:
        products = db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
        skus = {p.id: (p.client_sku or "").strip() for p in products}

    address = order.delivery_address if isinstance(order.delivery_address, dict) else None
    delivery = _delivery_text(address)
    product_rows = []
    for item in order.items:
        sku = skus.get(item.product_id or -1, "")
        product_rows.append(
            {
                "label": item.name,
                "description": item.name + (f" — livraison : {delivery}" if delivery else ""),
                "quantity": int(item.quantity),
                "unit_ht": float(item.unit_price_ht),
                "sku": sku,
            }
        )
    breakdown = order.shipping_breakdown if isinstance(order.shipping_breakdown, dict) else {}
    fee_rows: list[tuple[str, float, str]] = []
    shipping = float(order.shipping_amount or 0)
    if shipping > 0:
        fee_rows.append(
            (
                "Transport",
                shipping,
                "Frais de livraison" + (f" — {delivery}" if delivery else ""),
            )
        )
    for key, label in (
        ("dechargement", "Déchargement"),
        ("installation", "Installation"),
        ("totem_installation", "Installation totem"),
    ):
        amount = float(breakdown.get(key) or 0)
        if amount > 0:
            fee_rows.append((label, amount, label))

    try:
        result = issue_estimate(
            first_name=order.contact_first_name or "",
            last_name=order.contact_last_name or "",
            email=email,
            phone=order.contact_phone,
            client_reference=f"USER-{order.buyer_user_id}",
            subject=f"Devis n°{order.id}",
            note=(
                f"Demande Urbyn n°{order.id}."
                + (f" Livraison : {delivery}." if delivery else "")
            ),
            product_rows=product_rows,
            fee_rows=fee_rows,
            discount_ht=float(breakdown.get("discount") or 0),
        )
    except SellsyError as exc:
        result = {"email_sent": False, "message": f"Devis Sellsy non créé : {exc}"}
        logger.warning("Devis Sellsy commande %s : %s", order.id, exc)

    stored = dict(breakdown)
    stored["sellsy"] = result
    order.shipping_breakdown = stored
    db.commit()
