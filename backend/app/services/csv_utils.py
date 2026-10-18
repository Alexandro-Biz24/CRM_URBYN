"""Lecture CSV commune aux imports admin (encodage, séparateur, normalisation)."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.services.admin import AdminError

_URBYN_PATH_RE = re.compile(r"\[([^\]]+)\]")

_TRUE_VALUES = {"true", "vrai", "oui", "yes", "1", "abonne", "abonné"}
_FALSE_VALUES = {"false", "faux", "non", "no", "0", "non abonne", "non abonné"}


def read_csv_rows(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    sample = text[:4096]
    # Séparateur seulement. Les guillemets restent ceux d'Excel / Google Sheets
    # (un " dans une cellule est exporté ""). Le Sniffer met parfois doublequote=False
    # et coupe alors la cellule en plusieurs lignes.
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    dialect = csv.excel
    dialect.delimiter = delimiter
    dialect.doublequote = True

    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        raise AdminError("empty_csv", "Le fichier CSV est vide.")
    return rows


def norm_header(raw: str) -> str:
    return " ".join(raw.replace("\n", " ").replace("\r", " ").split()).strip().lower()


def row_dict(headers: list[str], values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, header in enumerate(headers):
        key = norm_header(header)
        if key:
            out[key] = values[i].strip() if i < len(values) else ""
    return out


def get_value(row: dict[str, str], *aliases: str) -> str:
    for alias in aliases:
        if row.get(alias):
            return row[alias]
    return ""


def require_headers(headers: list[str], required: dict[str, tuple[str, ...]]) -> None:
    """`required` : libellé affiché → alias normalisés acceptés."""
    present = {norm_header(h) for h in headers}
    missing = [label for label, aliases in required.items() if not present & set(aliases)]
    if missing:
        raise AdminError(
            "invalid_csv_headers",
            "Colonnes obligatoires manquantes : " + ", ".join(f"« {m} »" for m in missing) + ".",
        )


def normalize_name(raw: str) -> str:
    """Comparaison de noms : sans casse, accents ni espaces superflus."""
    text = unicodedata.normalize("NFKD", raw or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.casefold().split())


def parse_urbyn_paths(urbyn: str) -> list[list[str]]:
    paths: list[list[str]] = []
    for match in _URBYN_PATH_RE.findall(urbyn or ""):
        segments = [s.strip() for s in match.split("/") if s.strip()]
        if segments:
            paths.append(segments)
    return paths


def parse_decimal(raw: str) -> Decimal | None:
    text = (raw or "").strip().replace(" ", "").replace("\u00a0", "").replace("€", "")
    if not text:
        return None
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def parse_int(raw: str) -> int | None:
    value = parse_decimal(raw)
    if value is None or value != value.to_integral_value():
        return None
    return int(value)


def parse_bool(raw: str) -> bool | None:
    value = normalize_name(raw)
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None
