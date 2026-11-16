"""Écriture des patios saisis dans la feuille Hypothèses du tableur d'ombrage.

Lignes 6 à 15, une ligne par patio (1 à 10) :
A nom, B largeur A, C largeur B, D longueur C, E longueur D, en millimètres.
Les lignes sans patio sont vidées pour ne pas laisser une ancienne saisie.
"""

from __future__ import annotations

from typing import Any

from app.services.google_sheets import write_range

PATIO_SPREADSHEET_ID = "1r7jWmuul8BGGpxZnJlNoRK8MP33IF1gJ0wbYucarGII"
PATIO_HYPOTHESES_RANGE = "'Hypothèses'!A6:E15"
MAX_PATIOS = 10


def _millimetres(value: Any) -> int | float | str:
    """Le formulaire est en mètres. La feuille Hypothèses attend des millimètres."""
    if value is None or value == "":
        return ""
    mm = float(value) * 1000
    if mm.is_integer():
        return int(mm)
    return mm


def write_patio_hypotheses(patios: list[dict[str, Any]]) -> dict[str, Any]:
    """Remplit A6:E15. Un nom vide devient « patio 1 », « patio 2 », etc."""
    lignes = list(patios[:MAX_PATIOS])
    rows: list[list[Any]] = []
    for index in range(MAX_PATIOS):
        if index >= len(lignes):
            rows.append(["", "", "", "", ""])
            continue
        patio = lignes[index] or {}
        nom = str(patio.get("nom") or "").strip() or f"patio {index + 1}"
        rows.append(
            [
                nom,
                _millimetres(patio.get("largeur_a")),
                _millimetres(patio.get("largeur_b")),
                _millimetres(patio.get("longueur_c")),
                _millimetres(patio.get("longueur_d")),
            ]
        )
    write_range(PATIO_SPREADSHEET_ID, PATIO_HYPOTHESES_RANGE, rows)
    return {"ok": True, "rows": len(lignes), "range": PATIO_HYPOTHESES_RANGE}
