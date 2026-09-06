"""Orchestration Totem ↔ Google Sheets (vent / pression)."""

from __future__ import annotations

import time

from app.core.config import settings
from app.schemas.client_portal import (
    TotemWindSheetLookupRequest,
    TotemWindSheetLookupResponse,
    TotemWindSheetProductOut,
)
from app.services.google_sheets import GoogleSheetsError, lookup_product_column_value, write_two_cells
from app.services.totem_sheets_map import (
    region_to_sheet,
    resolve_sheet_totem_header,
    terrain_to_sheet,
)


class TotemWindSheetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def lookup_totem_wind_sheet(
    payload: TotemWindSheetLookupRequest,
) -> TotemWindSheetLookupResponse:
    region = region_to_sheet(payload.wind_zone)
    if not region:
        raise TotemWindSheetError("invalid_region", f"Zone vent invalide : {payload.wind_zone}")
    terrain = terrain_to_sheet(payload.terrain)
    if not terrain:
        raise TotemWindSheetError(
            "invalid_terrain",
            f"Terrain non mappé vers la sheet : {payload.terrain}",
        )

    # Résoudre les headers avant d'écrire (évite un write inutile si rien n'est supporté)
    resolved: list[tuple[object, str | None]] = []
    for p in payload.products:
        header = resolve_sheet_totem_header(
            product_name=p.product_name,
            client_sku=p.client_sku,
            cart_format=p.format,
        )
        resolved.append((p, header))

    write_ok = False
    settle = int(settings.GOOGLE_SHEETS_SETTLE_MS or 0)
    try:
        write_two_cells(region, terrain)
        write_ok = True
        if settle > 0:
            time.sleep(settle / 1000.0)
    except GoogleSheetsError as exc:
        raise TotemWindSheetError(exc.code, exc.message) from exc

    outs: list[TotemWindSheetProductOut] = []
    for p, header in resolved:
        if not header:
            outs.append(
                TotemWindSheetProductOut(
                    cart_item_id=p.cart_item_id,
                    product_id=p.product_id,
                    product_name=p.product_name,
                    sheet_header=None,
                    supported=False,
                    matched=False,
                    value=None,
                    message="Totem hors périmètre Google Sheet.",
                )
            )
            continue
        try:
            found = lookup_product_column_value(header)
        except GoogleSheetsError as exc:
            outs.append(
                TotemWindSheetProductOut(
                    cart_item_id=p.cart_item_id,
                    product_id=p.product_id,
                    product_name=p.product_name,
                    sheet_header=header,
                    supported=True,
                    matched=False,
                    value=None,
                    message=exc.message,
                )
            )
            continue
        outs.append(
            TotemWindSheetProductOut(
                cart_item_id=p.cart_item_id,
                product_id=p.product_id,
                product_name=p.product_name,
                sheet_header=header,
                supported=True,
                matched=bool(found.get("matched")),
                value=found.get("value"),
                message=None
                if found.get("matched")
                else f"Header « {header} » introuvable dans la plage sheet.",
            )
        )

    return TotemWindSheetLookupResponse(
        region_sheet=region,
        terrain_sheet=terrain,
        write_ok=write_ok,
        settle_ms=settle,
        products=outs,
    )
