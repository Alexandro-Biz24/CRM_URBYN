from pydantic import BaseModel, Field


class PricingLineIn(BaseModel):
    product_id: int
    supplier_tva: str
    quantity: int = Field(ge=1)


class PricingContextIn(BaseModel):
    postal_code: str = ""
    city: str = ""
    country: str = "FR"
    massif_transport: bool = False
    massif_dechargement: bool = False
    massif_installation: bool = False
    totem_transport: bool = False
    totem_installation: bool = False


class CartQuoteRequest(BaseModel):
    lines: list[PricingLineIn]
    context: PricingContextIn = PricingContextIn()


class EstimateRequest(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)
    cart: list[PricingLineIn] = []
    context: PricingContextIn = PricingContextIn()
