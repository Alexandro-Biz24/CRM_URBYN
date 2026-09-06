"""Mapping produits Totem (DB / panier) → libellés d'en-tête Google Sheets (ligne B21:P21).

Seuls les totems listés dans la sheet sont concernés :
80, 120, 160, 200 (= Caisson Bois),
SIGN-IZ, biface, SIGN-IZ 4 faces,
LIZ-60-800, LIZ-60-1000, LIZ-60-1000B, LIZ-90-800, LIZ-90-1000,
LIZ-Flèche - 1280, LIZ-30
"""

from __future__ import annotations

import re
from typing import Any

# Libellés EXACTS des en-têtes Google Sheet (à matcher casefold + espaces normalisés)
SHEET_TOTEM_HEADERS: tuple[str, ...] = (
    "80",
    "120",
    "160",
    "200",
    "SIGN-IZ",
    "biface",
    "SIGN-IZ 4 faces",
    "LIZ-60-800",
    "LIZ-60-1000",
    "LIZ-60-1000B",
    "LIZ-90-800",
    "LIZ-90-1000",
    "LIZ-Flèche - 1280",
    "LIZ-30",
)

# client_sku (Référence CSV / products.client_sku) → header sheet
SKU_TO_SHEET_HEADER: dict[str, str] = {
    "TOT-CB-80": "80",
    "TOT-CB-120": "120",
    "TOT-CB-160": "160",
    "TOT-CB-200": "200",
    # Sign-IZ biface (réf. connue en DB)
    "TOT-SIGN-2F": "SIGN-IZ",
    # LIZ — SKUs connus en CSV / DB
    "TOT-LIZ-60-800": "LIZ-60-800",
    "TOT-LIZ-60-1000": "LIZ-60-1000",
    "TOT-LIZ-60-1000-A": "LIZ-60-1000",  # variante acier même format
    "TOT-LIZ-60-1000B": "LIZ-60-1000B",
    "TOT-LIZ-60-1000-B": "LIZ-60-1000B",
    "TOT-LIZ-90-800": "LIZ-90-800",
    "TOT-LIZ-90-1000": "LIZ-90-1000",
    "TOT-LIZ-90-1000-A": "LIZ-90-1000",
    "TOT-LIZ-FLECHE-1280": "LIZ-Flèche - 1280",
    "TOT-LIZ-FLÈCHE-1280": "LIZ-Flèche - 1280",
    "TOT-LIZ-30": "LIZ-30",
}

# Terrain UI key → libellé EXACT dropdown sheet (B11)
# Front (TotemCompliancePage / wind-zones) → Google Sheet
TERRAIN_KEY_TO_SHEET: dict[str, str] = {
    "bord_mer": "Bord de mer",
    "rase_campagne": "Rase campagne",
    "campagne_haies": "Campagne avec haies",
    "zone_urbanisee": "Zone urbanisée",
    "zone_urbaine": "Zone urbaine (>15% surface)",
}

# Zone vent front (1..4, affichée « Zone de vent 2 ») → dropdown B10
# region_to_sheet(2) == "Région 2"


def _norm(value: str | None) -> str:
    return " ".join((value or "").strip().split()).casefold()


def region_to_sheet(zone: int | str | None) -> str | None:
    """Zone vent 1..4 → « Région N » (dropdown B10). « Région x » réservée (manuel)."""
    if zone is None:
        return None
    try:
        z = int(zone)
    except (TypeError, ValueError):
        raw = str(zone).strip()
        if raw.casefold().startswith("région"):
            return raw
        return None
    if z in (1, 2, 3, 4):
        return f"Région {z}"
    return None


def terrain_to_sheet(terrain_key_or_label: str | None) -> str | None:
    if not terrain_key_or_label:
        return None
    key = terrain_key_or_label.strip()
    if key in TERRAIN_KEY_TO_SHEET:
        return TERRAIN_KEY_TO_SHEET[key]
    # déjà un label sheet ?
    for label in TERRAIN_KEY_TO_SHEET.values():
        if _norm(label) == _norm(key):
            return label
    # label UI avec « surface bâtie »
    if "zone urbaine" in _norm(key):
        return TERRAIN_KEY_TO_SHEET["zone_urbaine"]
    return None


def resolve_sheet_totem_header(
    *,
    product_name: str | None = None,
    client_sku: str | None = None,
    cart_format: str | None = None,
    details: dict[str, Any] | None = None,
) -> str | None:
    """Retourne le libellé d'en-tête sheet à chercher dans B21:P21, ou None si hors périmètre."""
    d = details or {}
    sku = (client_sku or d.get("sku") or d.get("client_sku") or d.get("admin_sku") or "")
    sku = str(sku).strip().upper()
    if sku in SKU_TO_SHEET_HEADER:
        return SKU_TO_SHEET_HEADER[sku]

    name = (product_name or d.get("productName") or "").strip()
    fmt = (cart_format or d.get("format") or "").strip()
    blob = f"{name} {fmt}".strip()
    n = _norm(blob)

    # Caisson Bois 80/120/160/200 → header numérique
    m = re.search(r"caisson\s*bois\s*(\d{2,3})\b", n)
    if m and m.group(1) in {"80", "120", "160", "200"}:
        return m.group(1)
    # panier legacy format "80" + type caisson
    if re.fullmatch(r"80|120|160|200", _norm(fmt)) and "caisson" in n:
        return fmt.strip()

    # Sign-IZ
    if "sign-iz" in n or "sign iz" in n or _norm(fmt) == "sign-iz":
        if "4 face" in n or "4faces" in n.replace(" ", ""):
            return "SIGN-IZ 4 faces"
        if "biface" in n or "2 face" in n:
            return "biface"
        return "SIGN-IZ"

    # LIZ codes dans le nom / sku / format
    liz_patterns = [
        (r"liz[\s\-]?60[\s\-]?800\b", "LIZ-60-800"),
        (r"liz[\s\-]?60[\s\-]?1000b\b", "LIZ-60-1000B"),
        (r"liz[\s\-]?60[\s\-]?1000\b", "LIZ-60-1000"),
        (r"liz[\s\-]?90[\s\-]?800\b", "LIZ-90-800"),
        (r"liz[\s\-]?90[\s\-]?1000\b", "LIZ-90-1000"),
        (r"liz[\s\-]?fl[eè]che[^\d]*1280", "LIZ-Flèche - 1280"),
        (r"liz[\s\-]?30\b", "LIZ-30"),
    ]
    for pat, header in liz_patterns:
        if re.search(pat, n):
            return header

    # SKU partiel TOT-LIZ-*
    if sku.startswith("TOT-LIZ-"):
        code = sku.removeprefix("TOT-")
        # TOT-LIZ-60-1000-A → LIZ-60-1000
        code = re.sub(r"-A$", "", code)
        for h in SHEET_TOTEM_HEADERS:
            if _norm(h.replace(" ", "")) == _norm(code.replace(" ", "")):
                return h
            if _norm(h) == _norm(code.replace("LIZ-", "LIZ-")):
                return h

    return None


def is_sheet_supported_totem(**kwargs: Any) -> bool:
    return resolve_sheet_totem_header(**kwargs) is not None
