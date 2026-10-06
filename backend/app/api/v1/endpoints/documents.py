"""Fiches techniques totem — mapping clé produit → fichier Google Drive (proxy + cache)."""

from __future__ import annotations

import io
import json
import re
import threading
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import ROOT, settings

router = APIRouter()

_LOCAL_FICHES_DIR = Path(__file__).resolve().parents[2] / "static" / "fiches"

# Cache process-local (dev + Render single-instance). TTL long : les PDF changent rarement.
_PDF_CACHE_TTL_S = 6 * 3600
_TOKEN_SKEW_S = 120
_cache_lock = threading.Lock()
_pdf_cache: dict[str, tuple[float, bytes]] = {}  # file_id -> (expires_at, content)
_cached_token: str | None = None
_cached_token_expires_at: float = 0.0


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
    return _drive_map().get(key.casefold())


def _safe_filename(document_key: str) -> str:
    return f"fiche-technique-{document_key}.pdf"


def _local_pdf_path(document_key: str) -> Path | None:
    candidate = _LOCAL_FICHES_DIR / f"{document_key}.pdf"
    return candidate if candidate.is_file() else None


def _pdf_cache_get(file_id: str) -> bytes | None:
    now = time.time()
    with _cache_lock:
        hit = _pdf_cache.get(file_id)
        if hit is None:
            return None
        expires_at, content = hit
        if expires_at < now:
            _pdf_cache.pop(file_id, None)
            return None
        return content


def _pdf_cache_set(file_id: str, content: bytes) -> None:
    with _cache_lock:
        _pdf_cache[file_id] = (time.time() + _PDF_CACHE_TTL_S, content)


def _load_service_account_info() -> dict | None:
    raw = (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        return None
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


def _get_service_account_token() -> str:
    """Access token OAuth réutilisé jusqu'à expiration (évite un refresh Drive à chaque PDF)."""
    global _cached_token, _cached_token_expires_at

    now = time.time()
    with _cache_lock:
        if _cached_token and _cached_token_expires_at - _TOKEN_SKEW_S > now:
            return _cached_token

    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "google_auth_missing",
                "message": (
                    "Le package google-auth est manquant sur le serveur. "
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
    if not creds.token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "token_failed",
                "message": "Impossible d'obtenir un access token Google Drive.",
            },
        )

    expiry = getattr(creds, "expiry", None)
    expires_at = (
        expiry.timestamp()
        if expiry is not None
        else now + 3500
    )
    with _cache_lock:
        _cached_token = str(creds.token)
        _cached_token_expires_at = float(expires_at)
        return _cached_token


def _download_drive_public(file_id: str) -> bytes:
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
        return response.content


def _download_drive_service_account(file_id: str) -> bytes:
    token = _get_service_account_token()
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}
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
        return response.content


def _fetch_drive_pdf(file_id: str) -> bytes:
    cached = _pdf_cache_get(file_id)
    if cached is not None:
        return cached

    mode = (settings.FICHE_TECHNIQUE_DRIVE_MODE or "public").strip().lower()
    if mode == "service_account":
        content = _download_drive_service_account(file_id)
    else:
        content = _download_drive_public(file_id)

    _pdf_cache_set(file_id, content)
    return content


def _pdf_response(content: bytes, filename: str, *, cache_hit: bool = False) -> StreamingResponse:
    # Cache navigateur long : les fiches changent rarement.
    cache_control = "public, max-age=3600" if cache_hit else "public, max-age=600"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": cache_control,
            "X-Fiche-Cache": "HIT" if cache_hit else "MISS",
        },
    )


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
    Proxy PDF fiche technique (avec cache mémoire serveur).
    Clé = nom produit (ex. « Totem Caisson Bois 80 ») mappé dans FICHE_TECHNIQUE_DRIVE_MAP.
    """
    key = document_key.strip()
    if not key or ".." in key or "/" in key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_key", "message": "Clé document invalide."},
        )

    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", key).strip("-").lower() or "fiche"
    filename = _safe_filename(safe_slug)

    local = _local_pdf_path(safe_slug) or _local_pdf_path(key.casefold())
    if local is not None:
        return _pdf_response(local.read_bytes(), filename, cache_hit=True)

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

    cache_hit = _pdf_cache_get(file_id) is not None
    content = _fetch_drive_pdf(file_id)
    return _pdf_response(content, filename, cache_hit=cache_hit)
