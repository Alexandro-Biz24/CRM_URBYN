"""Fiches techniques totem — mapping clé produit → fichier Google Drive (proxy sécurisé)."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import ROOT, settings

router = APIRouter()

# Clés stables côté front (indépendantes du libellé affiché)
# Tu remplis les IDs Drive dans FICHE_TECHNIQUE_DRIVE_MAP (env).
DEFAULT_FICHE_KEYS = (
    "caisson-bois-80",
    "caisson-bois-120",
    "caisson-bois-160",
    "caisson-bois-200",
    "sign-iz",
)

_LOCAL_FICHES_DIR = Path(__file__).resolve().parents[2] / "static" / "fiches"


def _drive_map() -> dict[str, str]:
    raw = (settings.FICHE_TECHNIQUE_DRIVE_MAP or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "invalid_drive_map",
                "message": "FICHE_TECHNIQUE_DRIVE_MAP n'est pas un JSON valide.",
            },
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "invalid_drive_map",
                "message": "FICHE_TECHNIQUE_DRIVE_MAP doit être un objet JSON.",
            },
        )
    # Clés normalisées en minuscules (match sur nom produit)
    out: dict[str, str] = {}
    for k, v in data.items():
        key = str(k).strip()
        val = str(v).strip()
        if key and val:
            out[key.casefold()] = val
    return out


def _resolve_drive_file_id(document_key: str) -> str | None:
    key = document_key.strip()
    if not key:
        return None
    drive_map = _drive_map()
    return drive_map.get(key.casefold())


def _safe_filename(document_key: str) -> str:
    return f"fiche-technique-{document_key}.pdf"


def _local_pdf_path(document_key: str) -> Path | None:
    candidate = _LOCAL_FICHES_DIR / f"{document_key}.pdf"
    return candidate if candidate.is_file() else None


def _load_service_account_info() -> dict | None:
    raw = (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        return None
    # JSON inline (commence par {) vs chemin fichier
    if not raw.startswith("{"):
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "code": "invalid_service_account_json",
                        "message": f"JSON compte de service invalide ({path}).",
                    },
                ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "service_account_file_missing",
                "message": (
                    f"Fichier compte de service introuvable : {path}. "
                    "En prod (Render), colle le JSON complet dans "
                    "GOOGLE_SERVICE_ACCOUNT_JSON (pas un chemin local)."
                ),
            },
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "invalid_service_account_json",
                "message": "GOOGLE_SERVICE_ACCOUNT_JSON n'est pas un JSON valide.",
            },
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "invalid_service_account_json",
                "message": "GOOGLE_SERVICE_ACCOUNT_JSON doit être un objet JSON.",
            },
        )
    return data


def _download_drive_public(file_id: str) -> tuple[bytes, str]:
    """Télécharge un fichier partagé « avec le lien » (sans compte de service)."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        response = client.get(url)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "drive_unavailable",
                    "message": "Impossible de télécharger le PDF depuis Google Drive.",
                },
            )
        content_type = response.headers.get("content-type", "application/pdf")
        # Google peut renvoyer une page HTML de confirmation pour les gros fichiers
        if "text/html" in content_type.lower():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "drive_confirm_required",
                    "message": (
                        "Google Drive a bloqué le téléchargement direct. "
                        "Partage le fichier en lecture « avec le lien », ou configure "
                        "GOOGLE_SERVICE_ACCOUNT_JSON (mode service_account)."
                    ),
                },
            )
        return response.content, "application/pdf"


def _download_drive_service_account(file_id: str) -> tuple[bytes, str]:
    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "google_auth_missing",
                "message": (
                    "Le package google-auth est manquant sur le serveur. "
                    "Ajoute-le aux dépendances et redéploie. "
                    f"Détail: {exc}"
                ),
            },
        ) from exc

    info = _load_service_account_info()
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "drive_not_configured",
                "message": "GOOGLE_SERVICE_ACCOUNT_JSON manquant.",
            },
        )

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)

    # Refresh du token via httpx (évite la dépendance optionnelle « requests »)
    class _HttpxAuthResponse:
        def __init__(self, response: httpx.Response):
            self.status = response.status_code
            self.headers = response.headers
            self.data = response.content

    class _HttpxAuthRequest:
        def __call__(
            self,
            url,
            method="GET",
            body=None,
            headers=None,
            timeout=None,
            **_kwargs,
        ):
            with httpx.Client(timeout=timeout or 60.0) as client:
                response = client.request(method, url, content=body, headers=headers)
                return _HttpxAuthResponse(response)

    creds.refresh(_HttpxAuthRequest())

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "drive_unavailable",
                    "message": (
                        "Échec Drive API. Vérifie que le fichier est partagé avec "
                        "l'email du compte de service."
                    ),
                },
            )
        return response.content, "application/pdf"


@router.get("/fiche-technique/{document_key}/status")
def fiche_technique_status(document_key: str):
    """Indique si une fiche est disponible (mapping ou fichier local)."""
    key = document_key.strip()
    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", key).strip("-").lower() or "fiche"
    local = _local_pdf_path(safe_slug) is not None or _local_pdf_path(key.casefold()) is not None
    mapped = _resolve_drive_file_id(key) is not None
    return {
        "document_key": key,
        "available": local or mapped,
        "source": "local" if local else ("drive" if mapped else None),
    }


@router.get("/fiche-technique/{document_key}")
def download_fiche_technique(document_key: str):
    """
    Proxy PDF fiche technique.
    Clé = nom produit (ex. « Totem Caisson Bois 80 ») mappé dans FICHE_TECHNIQUE_DRIVE_MAP.
    """
    key = document_key.strip()
    if not key or ".." in key or "/" in key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_key", "message": "Clé document invalide."},
        )

    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", key).strip("-").lower() or "fiche"

    local = _local_pdf_path(safe_slug) or _local_pdf_path(key.casefold())
    if local is not None:
        data = local.read_bytes()
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{_safe_filename(safe_slug)}"',
                "Cache-Control": "private, max-age=300",
            },
        )

    file_id = _resolve_drive_file_id(key)
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_mapped",
                "message": (
                    f"Aucune fiche technique mappée pour « {key} ». "
                    "Ajoute l'ID Drive dans FICHE_TECHNIQUE_DRIVE_MAP."
                ),
            },
        )

    mode = (settings.FICHE_TECHNIQUE_DRIVE_MODE or "public").strip().lower()
    if mode == "service_account":
        content, media_type = _download_drive_service_account(file_id)
    else:
        content, media_type = _download_drive_public(file_id)

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_filename(safe_slug)}"',
            "Cache-Control": "private, max-age=300",
        },
    )
