from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from app.schemas.onboarding_company import EntrepriseSearchResult

logger = logging.getLogger(__name__)

API_URL = "https://recherche-entreprises.api.gouv.fr/search"
_TVA_IN_TEXT = re.compile(r"FR[\s.\-]*\d{2}[\s.\-]*\d{9}", re.IGNORECASE)


def _compact(query: str) -> str:
    return "".join(query.split()).upper().replace("-", "").replace(".", "")


def _siren_from_identifier(query: str) -> str | None:
    """SIREN (9), SIRET (14) ou TVA FR (clé + SIREN). None si c'est un nom."""
    compact = _compact(query)
    if compact.startswith("FR"):
        digits = "".join(c for c in compact[2:] if c.isdigit())
        if len(digits) != 11 or not compact[2:].isdigit():
            return None
        key = int(digits[:2])
        siren = digits[2:]
        expected = (12 + 3 * (int(siren) % 97)) % 97
        return siren if key == expected else None
    if not compact.isdigit():
        return None
    if len(compact) == 9:
        return compact
    if len(compact) == 14:
        return compact[:9]
    return None


def _compute_fr_vat(siren: str) -> str | None:
    digits = "".join(c for c in siren if c.isdigit())
    if len(digits) != 9:
        return None
    try:
        siren_int = int(digits)
    except ValueError:
        return None
    key = (12 + 3 * (siren_int % 97)) % 97
    return f"FR{key:02d}{digits}"


def _build_street(siege: dict) -> str | None:
    parts = [
        siege.get("numero_voie"),
        siege.get("type_voie"),
        siege.get("libelle_voie"),
        siege.get("complement_adresse"),
    ]
    line = " ".join(p.strip() for p in parts if p and str(p).strip())
    if line:
        return line
    geo = siege.get("geo_adresse") or siege.get("adresse")
    return str(geo).strip() if geo else None


def search_french_companies(query: str, *, limit: int = 8) -> list[EntrepriseSearchResult]:
    """
    API publique gratuite (data.gouv / INSEE) — alternative légère à Pappers.
    https://recherche-entreprises.api.gouv.fr
    """
    q = query.strip()
    if len(q) < 2:
        return []

    siren_lookup = _siren_from_identifier(q)
    if siren_lookup is None:
        embedded = _TVA_IN_TEXT.search(q)
        if embedded:
            siren_lookup = _siren_from_identifier(embedded.group(0))
    search_q = siren_lookup or q
    params = urllib.parse.urlencode({"q": search_q, "per_page": min(limit, 25)})
    url = f"{API_URL}?{params}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "urbyn-crm/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        logger.warning("Recherche entreprises HTTP %s: %s", exc.code, exc.read())
        return []
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Recherche entreprises indisponible: %s", exc)
        return []

    results: list[EntrepriseSearchResult] = []
    for item in data.get("results", []):
        siren = str(item.get("siren") or "").strip()
        if not siren:
            continue
        if siren_lookup and siren != siren_lookup:
            continue
        siege = item.get("siege") or {}
        siret = str(siege.get("siret") or "").strip() or None
        naf = item.get("activite_principale") or siege.get("activite_principale")
        name = (
            item.get("nom_complet")
            or item.get("nom_raison_sociale")
            or item.get("nom")
            or ""
        )
        results.append(
            EntrepriseSearchResult(
                company_name=str(name).strip(),
                siren=siren,
                siret=siret,
                tva_intra_com=_compute_fr_vat(siren),
                code_naf=str(naf).strip() if naf else None,
                street=_build_street(siege),
                zip_code=str(siege.get("code_postal") or "").strip() or None,
                city=str(siege.get("libelle_commune") or "").strip() or None,
                state=str(siege.get("departement") or "").strip() or None,
                country_code="FR",
            )
        )
    return results
