"""Tarification multi-fournisseur : une seule source de vérité.

Le montant affiché dans la pop-up est ce qui s'ajoute au panier :
prix effectif × quantité + surcoût de livraison du groupe
(même fournisseur et même adresse de départ).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Address,
    AddressCatalog,
    Catalog,
    CatalogProduct,
    Company,
    GeocodeCache,
    Product,
    ProductAttribut,
    RoadDistanceCache,
)
from app.repositories import admin_catalog_repo as catalog_repo
from app.repositories import supplier_offers_repo as offers_repo
from app.services.pricing_math import (
    TruckGroupKey,
    effective_unit_price,
    massif_handling_units,
    massif_truck_cost,
    massif_trucks,
    money,
    palettes_needed,
    totem_discount_rate,
    totem_truck_cost,
)

URBANIZE_TVA = catalog_repo._DEFAULT_URBANIZE_TVA


@dataclass
class CartLineIn:
    product_id: int
    supplier_tva: str
    quantity: int


@dataclass
class QuoteContext:
    postal_code: str
    city: str = ""
    country: str = "FR"
    massif_transport: bool = False
    massif_dechargement: bool = False
    massif_installation: bool = False
    totem_transport: bool = False
    totem_installation: bool = False


def _norm(value: str | None) -> str:
    return " ".join((value or "").replace("_", " ").casefold().split())


def _dec(raw: str | None) -> Decimal:
    text = (raw or "").strip().replace(" ", "").replace("€", "").replace(",", ".")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except Exception:
        return Decimal("0")


def _attr_value(db: Session, product_id: int, *needles: str) -> str:
    rows = db.scalars(
        select(ProductAttribut).where(ProductAttribut.product_id == product_id)
    ).all()
    for attr in rows:
        key = _norm(attr.name).replace(" ", "")
        if any(n.replace(" ", "") in key for n in needles):
            return (attr.value or "").strip()
    return ""


def _catalog_index(db: Session) -> dict[int, tuple[int | None, str]]:
    rows = db.execute(select(Catalog.id, Catalog.parent_id, Catalog.name)).all()
    return {cid: (parent_id, name or "") for cid, parent_id, name in rows}


def _catalog_path(index: dict[int, tuple[int | None, str]], catalog_id: int) -> list[str]:
    parts: list[str] = []
    seen: set[int] = set()
    current: int | None = catalog_id
    while current and current not in seen:
        seen.add(current)
        parent_id, name = index.get(current, (None, ""))
        parts.append(name)
        current = None if parent_id == current else parent_id
    parts.reverse()
    return parts


def _product_paths(db: Session, product_id: int) -> list[list[str]]:
    index = _catalog_index(db)
    catalog_ids = db.scalars(
        select(CatalogProduct.catalog_id).where(CatalogProduct.product_id == product_id)
    ).all()
    return [_catalog_path(index, cid) for cid in catalog_ids]


def _product_family(db: Session, product_id: int) -> str:
    """Massif et totem portent les camions. Accessoires et services sont des lignes simples."""
    paths = [[_norm(part) for part in path] for path in _product_paths(db, product_id)]
    for path in paths:
        if any(part in {"massif_service", "massif service"} for part in path):
            continue
        if any(part in {"massif", "lestage"} or part.startswith("massif ") for part in path):
            return "massif"
    for path in paths:
        if "totem" in path and "accessoire" not in path:
            return "totem"
    return "other"


def _catalog_ids_with_ancestors(db: Session, product_id: int) -> dict[int, int]:
    direct = set(
        db.scalars(
            select(CatalogProduct.catalog_id).where(CatalogProduct.product_id == product_id)
        ).all()
    )
    depth = {cid: 0 for cid in direct}
    frontier = set(direct)
    level = 0
    while frontier and level < 32:
        level += 1
        rows = db.execute(
            select(Catalog.id, Catalog.parent_id).where(Catalog.id.in_(frontier))
        ).all()
        nxt: set[int] = set()
        for cid, parent_id in rows:
            if parent_id is None or parent_id == cid or parent_id in depth:
                continue
            depth[parent_id] = level
            nxt.add(parent_id)
        frontier = nxt
    return depth


def _own_departure_address(db: Session, supplier_tva: str) -> Address | None:
    """Siège ou adresse principale du fournisseur, quand aucun catalogue n'est lié."""
    addrs = [
        addr
        for addr in db.scalars(
            select(Address)
            .where(Address.company_tva_intra_com == supplier_tva)
            .order_by(Address.is_primary.desc(), Address.id.asc())
        ).all()
        if (addr.zip_code or "").strip()
    ]
    if not addrs:
        return None
    for addr in addrs:
        label = (addr.label or "").lower().replace("è", "e").replace("é", "e")
        if "siege" in label:
            return addr
    for addr in addrs:
        if addr.is_primary:
            return addr
    return addrs[0]


def supplier_origin(db: Session, product_id: int, supplier_tva: str) -> Address | None:
    """Adresse de départ : catalogue du produit si elle est liée, sinon le siège du fournisseur."""
    depth = _catalog_ids_with_ancestors(db, product_id)
    if depth:
        rows = db.execute(
            select(Address, AddressCatalog.catalog_id)
            .join(AddressCatalog, AddressCatalog.address_id == Address.id)
            .where(
                Address.company_tva_intra_com == supplier_tva,
                AddressCatalog.catalog_id.in_(depth.keys()),
            )
        ).all()
        best: Address | None = None
        best_key: tuple[int, int] | None = None
        for addr, catalog_id in rows:
            if not (addr.zip_code or "").strip():
                continue
            key = (depth.get(catalog_id, 10**9), addr.id)
            if best_key is None or key < best_key:
                best, best_key = addr, key
        if best is not None:
            return best
    return _own_departure_address(db, supplier_tva)


def _geocode(db: Session, postal_code: str, city: str) -> tuple[float, float] | None:
    pc = postal_code.strip()
    key = f"{pc}|{_norm(city)}|fr"
    cached = db.get(GeocodeCache, key)
    if cached is not None:
        return cached.lat, cached.lng
    if len(pc) < 5:
        return None
    try:
        response = httpx.get(
            "https://geo.api.gouv.fr/communes",
            params={"codePostal": pc, "fields": "nom,centre", "format": "json"},
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    chosen = data[0]
    city_key = _norm(city)
    if city_key:
        for item in data:
            if _norm(item.get("nom")) == city_key:
                chosen = item
                break
    coords = (chosen.get("centre") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    lng, lat = float(coords[0]), float(coords[1])
    db.add(GeocodeCache(query_key=key, lat=lat, lng=lng, created_at=datetime.utcnow()))
    db.flush()
    return lat, lng


def road_distance_km(
    db: Session,
    origin_zip: str,
    origin_city: str,
    dest_zip: str,
    dest_city: str,
) -> Decimal:
    origin = _geocode(db, origin_zip, origin_city)
    dest = _geocode(db, dest_zip, dest_city)
    if origin is None or dest is None:
        return Decimal("0")
    origin_key = f"{origin[0]:.5f},{origin[1]:.5f}"
    dest_key = f"{dest[0]:.5f},{dest[1]:.5f}"
    cached = db.scalar(
        select(RoadDistanceCache).where(
            RoadDistanceCache.origin_key == origin_key,
            RoadDistanceCache.dest_key == dest_key,
        )
    )
    if cached is not None:
        return Decimal(str(cached.km))
    km = 0.0
    source = "haversine"
    try:
        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{origin[1]},{origin[0]};{dest[1]},{dest[0]}?overview=false"
        )
        response = httpx.get(url, timeout=8)
        response.raise_for_status()
        meters = response.json()["routes"][0]["distance"]
        km = meters / 1000
        source = "osrm"
    except Exception:
        km = _haversine_km(origin, dest) * 1.3
    db.add(
        RoadDistanceCache(
            origin_key=origin_key,
            dest_key=dest_key,
            km=km,
            source=source,
            created_at=datetime.utcnow(),
        )
    )
    db.flush()
    return Decimal(str(round(km)))


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import atan2, cos, radians, sin, sqrt

    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * atan2(sqrt(h), sqrt(1 - h))


def _offer_unit(db: Session, product_id: int, supplier_tva: str) -> tuple[Decimal, int] | None:
    offer = offers_repo.latest_offer(db, supplier_tva, product_id)
    if offer is None:
        return None
    sub = offers_repo.get_subscription(db, supplier_tva)
    abonne = bool(sub and sub.abonne)
    unit = effective_unit_price(Decimal(str(offer.price)), Decimal(str(offer.urbyn_marge)), abonne)
    return unit, int(offer.delai_jours)


def _named_product(db: Session, path_parts: list[str], product_name: str) -> Product | None:
    """Produit dont le nom correspond et dont un chemin catalogue contient chaque segment."""
    needles = [_norm(part) for part in path_parts]
    target = _norm(product_name)
    index = _catalog_index(db)
    rows = db.execute(
        select(Product, CatalogProduct.catalog_id)
        .join(CatalogProduct, CatalogProduct.product_id == Product.id)
    ).all()
    for product, catalog_id in rows:
        if _norm(product.product_name) != target:
            continue
        path = [_norm(part) for part in _catalog_path(index, catalog_id)]
        if all(needle in path for needle in needles):
            return product
    return None


@dataclass
class _ReadyLine:
    product_id: int
    name: str
    supplier_tva: str
    supplier_name: str
    quantity: int
    family: str
    unit_weight: Decimal
    per_palette: int
    unit_price: Decimal
    delay_days: int
    address_id: int | None
    origin_zip: str
    origin_city: str
    distance_km: Decimal


def _prepare_line(
    db: Session, line: CartLineIn, dest_zip: str, dest_city: str, ctx: QuoteContext
) -> _ReadyLine | None:
    product = db.get(Product, line.product_id)
    priced = _offer_unit(db, line.product_id, line.supplier_tva)
    if product is None or priced is None or line.quantity <= 0:
        return None
    unit, delay = priced
    company = db.get(Company, line.supplier_tva)
    family = _product_family(db, product.id)
    origin = supplier_origin(db, line.product_id, line.supplier_tva)
    needs_road = (family == "massif" and ctx.massif_transport) or (
        family == "totem" and ctx.totem_transport
    )
    distance = Decimal("0")
    if needs_road and origin is not None and dest_zip:
        distance = road_distance_km(
            db, origin.zip_code or "", origin.city or "", dest_zip, dest_city
        )
    per_palette_raw = _attr_value(db, product.id, "palette")
    return _ReadyLine(
        product_id=product.id,
        name=product.product_name,
        supplier_tva=line.supplier_tva,
        supplier_name=company.company_name if company else line.supplier_tva,
        quantity=line.quantity,
        family=family,
        unit_weight=_dec(_attr_value(db, product.id, "poids")),
        per_palette=int(_dec(per_palette_raw)),
        unit_price=unit,
        delay_days=delay,
        address_id=origin.id if origin else None,
        origin_zip=(origin.zip_code or "") if origin else "",
        origin_city=(origin.city or "") if origin else "",
        distance_km=distance,
    )


def _service_unit(db: Session, path_parts: list[str], name: str, supplier_tva: str) -> Decimal:
    product = _named_product(db, path_parts, name)
    if product is None:
        return Decimal("0")
    priced = _offer_unit(db, product.id, supplier_tva)
    return priced[0] if priced else Decimal("0")


def quote_lines(db: Session, lines: list[CartLineIn], ctx: QuoteContext) -> dict:
    ready = [
        item
        for line in lines
        if (item := _prepare_line(db, line, ctx.postal_code, ctx.city, ctx))
        is not None
    ]
    products_ht = Decimal("0")
    totem_ht_by_supplier: dict[str, Decimal] = {}
    totem_qty_by_supplier: dict[str, int] = {}
    massif_groups: dict[TruckGroupKey, list[_ReadyLine]] = {}
    totem_groups: dict[TruckGroupKey, list[_ReadyLine]] = {}
    palette_qty: dict[str, int] = {}
    install_units = 0
    max_delay = 0

    for line in ready:
        if _norm(line.name) == "palette":
            continue
        products_ht += line.unit_price * line.quantity
        max_delay = max(max_delay, line.delay_days)
        if line.family == "totem":
            totem_ht_by_supplier[line.supplier_tva] = (
                totem_ht_by_supplier.get(line.supplier_tva, Decimal("0"))
                + line.unit_price * line.quantity
            )
            totem_qty_by_supplier[line.supplier_tva] = (
                totem_qty_by_supplier.get(line.supplier_tva, 0) + line.quantity
            )
        if line.family == "massif" and line.address_id is not None:
            key = TruckGroupKey(line.supplier_tva, line.address_id)
            massif_groups.setdefault(key, []).append(line)
            palettes = palettes_needed(line.quantity, line.per_palette)
            palette_qty[line.supplier_tva] = palette_qty.get(line.supplier_tva, 0) + palettes
            install_units += massif_handling_units(line.quantity, line.per_palette)
        if line.family == "totem" and line.address_id is not None:
            key = TruckGroupKey(line.supplier_tva, line.address_id)
            totem_groups.setdefault(key, []).append(line)

    discount = Decimal("0")
    discount_by_supplier: dict[str, Decimal] = {}
    for tva, ht in totem_ht_by_supplier.items():
        amount = money(ht * totem_discount_rate(totem_qty_by_supplier[tva]))
        discount += amount
        discount_by_supplier[tva] = amount

    shipping = Decimal("0")
    shipping_by_supplier: dict[str, Decimal] = {}
    massif_truck_count = 0
    if ctx.massif_transport:
        for key, group in massif_groups.items():
            weight = sum((line.unit_weight * line.quantity for line in group), Decimal("0"))
            trucks = massif_trucks(weight)
            massif_truck_count += trucks
            cost = massif_truck_cost(weight, group[0].distance_km, trucks)
            shipping += cost
            shipping_by_supplier[key.supplier_tva] = (
                shipping_by_supplier.get(key.supplier_tva, Decimal("0")) + cost
            )
    if ctx.totem_transport:
        for key, group in totem_groups.items():
            qty = sum(line.quantity for line in group)
            cost = totem_truck_cost(qty, group[0].distance_km)
            shipping += cost
            shipping_by_supplier[key.supplier_tva] = (
                shipping_by_supplier.get(key.supplier_tva, Decimal("0")) + cost
            )

    dechargement = Decimal("0")
    installation = Decimal("0")
    palettes_ht = Decimal("0")
    if ctx.massif_transport and ctx.massif_dechargement and massif_truck_count:
        unit = _service_unit(db, ["Massif_Service"], "Déchargement", URBANIZE_TVA)
        dechargement = money(unit * massif_truck_count)
    if ctx.massif_transport and ctx.massif_dechargement and ctx.massif_installation and install_units:
        unit = _service_unit(db, ["Massif_Service"], "Installation", URBANIZE_TVA)
        installation = money(unit * install_units)
    for tva, qty in palette_qty.items():
        if qty <= 0:
            continue
        unit = _service_unit(db, ["Massif_Service"], "Palette", tva)
        if unit == 0:
            unit = _service_unit(db, ["Massif", "Accessoire"], "Palette", tva)
        palettes_ht += money(unit * qty)

    totem_install = Decimal("0")
    totem_qty = sum(totem_qty_by_supplier.values())
    if ctx.totem_installation and totem_qty:
        unit = _service_unit(db, ["Totem", "Accessoire"], "Installation complète", URBANIZE_TVA)
        totem_install = money(unit * totem_qty)

    total = money(products_ht - discount + palettes_ht + shipping + dechargement + installation + totem_install)
    return {
        "products_ht": float(money(products_ht)),
        "discount": float(money(discount)),
        "palettes_ht": float(money(palettes_ht)),
        "shipping": float(money(shipping)),
        "dechargement": float(money(dechargement)),
        "installation": float(money(installation)),
        "totem_installation": float(money(totem_install)),
        "total": float(total),
        "delay_days": max_delay,
        "massif_trucks": massif_truck_count,
        "shipping_by_supplier": {
            tva: float(money(amount)) for tva, amount in shipping_by_supplier.items()
        },
        "discount_by_supplier": {
            tva: float(money(amount)) for tva, amount in discount_by_supplier.items()
        },
        "_total": total,
        "_shipping": money(shipping + dechargement),
    }


def estimate_product(
    db: Session,
    *,
    product_id: int,
    quantity: int,
    cart: list[CartLineIn],
    ctx: QuoteContext,
) -> dict:
    """Une simulation par fournisseur qui propose le produit et a une adresse."""
    offers = offers_repo.latest_offers_for_products(db, [product_id])
    baseline = quote_lines(db, cart, ctx)
    family = _product_family(db, product_id)
    needs_origin = (family == "massif" and ctx.massif_transport) or (
        family == "totem" and ctx.totem_transport
    )
    segments_input: list[dict] = []
    for offer in offers:
        origin = supplier_origin(db, product_id, offer.company_tva_intra_com)
        if needs_origin and origin is None:
            continue
        scenario = cart + [
            CartLineIn(product_id, offer.company_tva_intra_com, quantity)
        ]
        quoted = quote_lines(db, scenario, ctx)
        added = money(quoted["_total"] - baseline["_total"])
        added_shipping = money(quoted["_shipping"] - baseline["_shipping"])
        company = db.get(Company, offer.company_tva_intra_com)
        priced = _offer_unit(db, product_id, offer.company_tva_intra_com)
        segments_input.append(
            {
                "supplier_tva": offer.company_tva_intra_com,
                "supplier_name": company.company_name if company else offer.company_tva_intra_com,
                "unit_price": float(priced[0]) if priced else float(offer.price),
                "delay_days": int(offer.delai_jours),
                "added_total": float(added),
                "added_shipping": float(added_shipping),
                "order_total": quoted["total"],
                "_added": added,
                "_ship": added_shipping,
            }
        )

    def _public(row: dict) -> dict:
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def _best(rows: list[dict], key) -> dict | None:
        if not rows:
            return None
        return _public(min(rows, key=key))

    prix = _best(segments_input, lambda r: (r["_added"], r["delay_days"]))
    livraison = (
        _best(segments_input, lambda r: (r["_ship"], r["_added"]))
        if ctx.massif_transport or ctx.totem_transport
        else None
    )
    delai = _best(segments_input, lambda r: (r["delay_days"], r["_added"]))
    return {
        "product_id": product_id,
        "quantity": quantity,
        "offers": [_public(row) for row in segments_input],
        "segments": {"prix": prix, "livraison": livraison, "delai": delai},
    }
