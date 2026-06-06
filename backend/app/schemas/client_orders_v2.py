from pydantic import BaseModel, Field


class CartLineCreateV2(BaseModel):
    """Ligne panier : produit catalogue + quantité."""

    product_id: int = Field(..., ge=1)
    quantity: int = Field(..., ge=1)


class ClientCheckoutCreateV2(BaseModel):
    """
    Validation panier → une ou plusieurs commandes (`orders` + `product_order`).

    Les lignes peuvent concerner **plusieurs fournisseurs** (TVA / `companies_id` différentes) :
    le backend crée **une commande par fournisseur** présent dans le panier.

    Le champ vendeur côté base / API n’est pas utilisé pour l’instant.
    """

    buyer_id: int = Field(..., ge=1)
    items: list[CartLineCreateV2] = Field(..., min_length=1)
    status: str = Field(
        "pending",
        description="Statut commande (ex: pending, paid, cancelled)",
    )
    currency: str = Field("EUR", min_length=3, max_length=3)
    shipping_amount: float = Field(0, ge=0)
    tax_amount: float = Field(0, ge=0)
    shipping_address_id: int | None = None
    invoice_address_id: int | None = None
    decrement_stock: bool = Field(
        True,
        description="Si True, décrémente stock sur company_catalog_items",
    )


class ClientCheckoutOrderPartV2(BaseModel):
    """Une commande créée (un fournisseur)."""

    order_id: int
    company_id: str = Field(description="TVA intracom du fournisseur")
    subtotal: float
    tax_amount: float
    shipping_amount: float
    total_amount: float
    product_order_ids: list[int]


class ClientCheckoutCreatedV2(BaseModel):
    buyer_id: int
    currency: str
    orders: list[ClientCheckoutOrderPartV2]
