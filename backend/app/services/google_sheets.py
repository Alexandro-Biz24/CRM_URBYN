"""Client Google Sheets (module NOUVEAU — n'altère aucun flux existant).

Flux métier (vent / totem) :
1. Écrire Région (cellule 1) + Catégorie Terrain (cellule 2) — dropdowns
2. Laisser Sheets recalculer
3. Chercher le produit (totem) dans la ligne d'en-têtes (ex. B21:P21)
4. Lire la valeur sur la même colonne, ligne résultats (ex. B46:P46)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import ROOT, settings

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class GoogleSheetsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _a1_with_sheet(cell_or_range: str) -> str:
    """Préfixe le nom d'onglet env si l'adresse A1 n'en a pas déjà un."""
    ref = (cell_or_range or "").strip()
    if not ref:
        raise GoogleSheetsError("missing_ref", "Adresse de cellule / plage manquante.")
    if "!" in ref:
        return ref
    sheet = (settings.GOOGLE_SHEETS_SHEET_NAME or "").strip()
    if not sheet:
        return ref
    safe = sheet.replace("'", "''")
    return f"'{safe}'!{ref}"


def sheets_config_ready() -> tuple[bool, list[str]]:
    """Retourne (ok, liste des champs manquants)."""
    missing: list[str] = []
    checks = {
        "GOOGLE_SHEETS_SPREADSHEET_ID": settings.GOOGLE_SHEETS_SPREADSHEET_ID,
        "GOOGLE_SHEETS_WRITE_CELL_1": settings.GOOGLE_SHEETS_WRITE_CELL_1,
        "GOOGLE_SHEETS_WRITE_CELL_2": settings.GOOGLE_SHEETS_WRITE_CELL_2,
        "GOOGLE_SHEETS_LOOKUP_HEADER_RANGE": settings.GOOGLE_SHEETS_LOOKUP_HEADER_RANGE,
        "GOOGLE_SHEETS_LOOKUP_VALUE_RANGE": settings.GOOGLE_SHEETS_LOOKUP_VALUE_RANGE,
    }
    for key, val in checks.items():
        if not (val or "").strip():
            missing.append(key)
    cred = (
        (settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON or "").strip()
        or (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    )
    if not cred:
        missing.append(
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON (ou GOOGLE_SERVICE_ACCOUNT_JSON)"
        )
    return (len(missing) == 0, missing)


def _load_service_account_info() -> dict[str, Any]:
    raw = (
        (settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON or "").strip()
        or (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    )
    if not raw:
        raise GoogleSheetsError(
            "missing_credentials",
            "Aucune credential Google Sheets : définis "
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON ou GOOGLE_SERVICE_ACCOUNT_JSON.",
        )

    if not raw.startswith("{"):
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise GoogleSheetsError(
                "credentials_file_missing",
                f"Fichier compte de service introuvable : {path}",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GoogleSheetsError(
                "invalid_credentials_json",
                f"JSON compte de service invalide ({path}).",
            ) from exc
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GoogleSheetsError(
                "invalid_credentials_json",
                "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON n'est pas un JSON valide.",
            ) from exc

    if not isinstance(data, dict):
        raise GoogleSheetsError(
            "invalid_credentials_json",
            "Les credentials Google Sheets doivent être un objet JSON.",
        )
    return data


def _access_token() -> str:
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise GoogleSheetsError(
            "google_auth_missing",
            "Package google-auth manquant. Installe les deps backend.",
        ) from exc

    info = _load_service_account_info()
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=[SHEETS_SCOPE]
    )
    creds.refresh(Request())
    if not creds.token:
        raise GoogleSheetsError(
            "token_failed",
            "Impossible d'obtenir un access token Google Sheets.",
        )
    return str(creds.token)


def _spreadsheet_id() -> str:
    sid = (settings.GOOGLE_SHEETS_SPREADSHEET_ID or "").strip()
    if not sid:
        raise GoogleSheetsError(
            "missing_spreadsheet_id",
            "GOOGLE_SHEETS_SPREADSHEET_ID manquant.",
        )
    return sid


def _require_write_config() -> None:
    need: list[str] = []
    if not (settings.GOOGLE_SHEETS_SPREADSHEET_ID or "").strip():
        need.append("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not (settings.GOOGLE_SHEETS_WRITE_CELL_1 or "").strip():
        need.append("GOOGLE_SHEETS_WRITE_CELL_1")
    if not (settings.GOOGLE_SHEETS_WRITE_CELL_2 or "").strip():
        need.append("GOOGLE_SHEETS_WRITE_CELL_2")
    cred = (
        (settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON or "").strip()
        or (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    )
    if not cred:
        need.append("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON (ou GOOGLE_SERVICE_ACCOUNT_JSON)")
    if need:
        raise GoogleSheetsError(
            "config_incomplete",
            "Config Sheets incomplète pour l'écriture : " + ", ".join(need),
        )


def _get_values(range_a1: str, *, major: str = "ROWS") -> list[list[Any]]:
    token = _access_token()
    url = f"{SHEETS_API}/{_spreadsheet_id()}/values/{quote(range_a1, safe='')}"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"majorDimension": major, "valueRenderOption": "UNFORMATTED_VALUE"},
        )
    if resp.status_code >= 400:
        raise GoogleSheetsError(
            "sheets_read_failed",
            f"Lecture Sheets HTTP {resp.status_code}: {resp.text[:500]}",
        )
    return list((resp.json() or {}).get("values") or [])


def write_two_cells(value_1: Any, value_2: Any) -> dict[str, Any]:
    """Écrit Région + Catégorie Terrain (GOOGLE_SHEETS_WRITE_CELL_1/2)."""
    _require_write_config()

    cell1 = _a1_with_sheet(settings.GOOGLE_SHEETS_WRITE_CELL_1)
    cell2 = _a1_with_sheet(settings.GOOGLE_SHEETS_WRITE_CELL_2)
    token = _access_token()
    url = f"{SHEETS_API}/{_spreadsheet_id()}/values:batchUpdate"
    body = {
        "valueInputOption": "USER_ENTERED",
        "data": [
            {"range": cell1, "values": [[value_1]]},
            {"range": cell2, "values": [[value_2]]},
        ],
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
    if resp.status_code >= 400:
        raise GoogleSheetsError(
            "sheets_write_failed",
            f"Écriture Sheets HTTP {resp.status_code}: {resp.text[:500]}",
        )
    return {
        "ok": True,
        "cell_1": cell1,
        "cell_2": cell2,
        "value_1": value_1,
        "value_2": value_2,
        "response": resp.json(),
    }


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def lookup_product_column_value(product_name: Any) -> dict[str, Any]:
    """Cherche ``product_name`` dans la ligne header (B21:P21),
    renvoie la valeur de la même colonne sur la ligne value (B46:P46).
    """
    header_raw = (settings.GOOGLE_SHEETS_LOOKUP_HEADER_RANGE or "").strip()
    value_raw = (settings.GOOGLE_SHEETS_LOOKUP_VALUE_RANGE or "").strip()
    if not header_raw or not value_raw:
        raise GoogleSheetsError(
            "config_incomplete",
            "GOOGLE_SHEETS_LOOKUP_HEADER_RANGE et "
            "GOOGLE_SHEETS_LOOKUP_VALUE_RANGE sont requis.",
        )

    header_a1 = _a1_with_sheet(header_raw)
    value_a1 = _a1_with_sheet(value_raw)

    # ROWS → une ligne = liste de cellules ; on aplatit si besoin
    header_rows = _get_values(header_a1, major="ROWS")
    value_rows = _get_values(value_a1, major="ROWS")
    headers = header_rows[0] if header_rows else []
    values = value_rows[0] if value_rows else []

    needle = _norm_label(product_name)
    if not needle:
        raise GoogleSheetsError("empty_product", "Nom de produit / totem vide.")

    matched_index: int | None = None
    matched_header: str | None = None
    for i, cell in enumerate(headers):
        if _norm_label(cell) == needle:
            matched_index = i
            matched_header = "" if cell is None else str(cell).strip()
            break

    if matched_index is None:
        return {
            "ok": True,
            "matched": False,
            "product_name": product_name,
            "header_range": header_a1,
            "value_range": value_a1,
            "column_index": None,
            "header": None,
            "value": None,
        }

    result = values[matched_index] if matched_index < len(values) else None
    return {
        "ok": True,
        "matched": True,
        "product_name": product_name,
        "header_range": header_a1,
        "value_range": value_a1,
        "column_index": matched_index,
        "header": matched_header,
        "value": result,
    }


# Alias historique (si un appelant utilisait encore lookup_in_range)
def lookup_in_range(match_value: Any) -> dict[str, Any]:
    return lookup_product_column_value(match_value)


def write_and_lookup(
    region: Any,
    terrain_category: Any,
    *,
    product_name: Any,
    settle_ms: int | None = None,
) -> dict[str, Any]:
    """Écrit les 2 dropdowns, attend le recalcul Sheets, puis lookup produit."""
    written = write_two_cells(region, terrain_category)
    delay = settings.GOOGLE_SHEETS_SETTLE_MS if settle_ms is None else settle_ms
    if delay and delay > 0:
        time.sleep(delay / 1000.0)
    found = lookup_product_column_value(product_name)
    return {"write": written, "lookup": found, "settle_ms": delay}
