from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.pricing import CartQuoteRequest, EstimateRequest
from app.services.pricing import CartLineIn, QuoteContext, estimate_product, quote_lines

router = APIRouter()


def _lines(rows) -> list[CartLineIn]:
    return [CartLineIn(row.product_id, row.supplier_tva, row.quantity) for row in rows]


def _context(raw) -> QuoteContext:
    return QuoteContext(
        postal_code=raw.postal_code,
        city=raw.city,
        country=raw.country,
        massif_transport=raw.massif_transport,
        massif_dechargement=raw.massif_dechargement,
        massif_installation=raw.massif_installation,
        totem_transport=raw.totem_transport,
        totem_installation=raw.totem_installation,
    )


def _public(quoted: dict) -> dict:
    return {key: value for key, value in quoted.items() if not key.startswith("_")}


@router.post("/cart")
def price_cart(body: CartQuoteRequest, db: Session = Depends(get_db)) -> dict:
    quoted = quote_lines(db, _lines(body.lines), _context(body.context))
    db.commit()
    return _public(quoted)


@router.post("/estimate")
def price_estimate(body: EstimateRequest, db: Session = Depends(get_db)) -> dict:
    result = estimate_product(
        db,
        product_id=body.product_id,
        quantity=body.quantity,
        cart=_lines(body.cart),
        ctx=_context(body.context),
    )
    db.commit()
    return result
