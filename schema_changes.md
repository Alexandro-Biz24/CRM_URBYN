# Modifications de schéma – historique

## 2026-03-25 – DEMANDE.md (orders / company / produits)

### Renommages

- `order_items` -> **`product_order`** (modèle `ProductOrder` dans `order_item.py`).
- Colonne `catalog_item_id` remplacée par **`product_id`** (FK -> `products.id`).
- `attribut_produit` -> **`product_attribut`** (modèle `ProductAttribut`).

### Suppressions

- Table / modèle **`order_addresses`** supprimé.
- Table / modèle **`company_translations`** supprimé.
- Table / modèle **`product_shipping`** supprimé.

### `orders`

- Ajout de **`shipping_address_id`** (FK -> `addresses.id`).
- Ajout de **`invoice_address_id`** (FK -> `addresses.id`).
- Relations ORM ajoutées : `shipping_address`, `invoice_address`.

### `companies`

- Ajout de **`VAT_rate`** (attribut ORM `vat_rate`, colonne SQL `"VAT_rate"`).

### Impacts ORM

- `Service.order_items` renommé en `Service.product_orders`.
- `Product.product_orders` ajouté.
- Requêtes metrics adaptées à `product_order` + `products` (plus `order_items`/`catalog_item_id`).

---

## 2026-03-23 – DEMANDE.md (catalogue, produits, avis, services)

### Supprimé

- Tables / modèles **`categories`**, **`category_translations`**, **`product_components`**.

### `catalogs`

- **`parent_id`** (nullable, FK → `catalogs.id`) : hiérarchie de catalogues.

### `catalog_items`

- Supprimé : **`product_id`**, **`company_id`** (prix/stock société déplacés).
- Ajouté : **`service_id`** (nullable, FK → `services.id`).

### `company_catalog_items` (nouvelle table)

- `id`, **`company_id`** (TVA → `companies.tva_intra_com`), **`catalog_item_id`**, `custom_price`, `currency`, `stock_quantity`, `is_available`, timestamps.
- Contrainte d’unicité `(company_id, catalog_item_id)`.

### `products`

- **`catalog_item_id`** (FK → `catalog_items.id`, **unique** : 1 produit par ligne catalogue).
- **`companies_id`** (colonne SQL, FK → `companies.tva_intra_com`) — attribut ORM `company_tva_intra_com`.
- Supprimé : **`category_id`**, relations composants.
- Nouvelles tables liées : **`product_price_history`**, **`attribu_produit`**.
- Ajout de champs produit (d’après captures) :
  - `teinte`
  - `type_de_produit`
  - `gamme`
  - `duree_garantie`
  - `conditions_garantie`
  - `piece_ouvrage_destination`
  - `traitement_bois_classification`
  - `produit_nuance`
  - `description_profil`
  - `couleur_traitement_autoclave`
  - `code_douane_sh8`
  - `type_bois`
  - `essence_bois`
  - `longueur`, `largeur`, `hauteur`, `volume`, `poids_net`

### `services`

- Supprimé : **`category_id`**.
- Ajouté : **`service_type`**.

### `reviews`

- Supprimé : **`product_id`**, **`service_id`**.
- Ajouté : **`company_id`** (TVA → `companies.tva_intra_com`) — attribut ORM `company_tva_intra_com`.

### Code

- **`metrics_repo`** : agrégations fournisseur via **`company_catalog_items`** (plus `catalog_items.company_id`).
- **`Company`** : `company_catalog_items`, `products`, `reviews` ; plus de relation directe `catalog_items`.

**Migration Alembic** : à générer / adapter (données existantes : recréer `company_catalog_items` à partir des anciennes lignes `catalog_items` + `company_id`, puis lier les `products`).

---

## 2026-03-11 – DEMANDE.md (rôles, société TVA PK, liaisons, banque, adresses)

### Nouvelles tables

- **`roles`** (`role.py`) : `id`, `role_name` (ex. `Fournisseur`, `client`, `admin`).
- **`companies_users`** (`company_user.py`) : `id`, `user_id` → `users`, `company_id` → `companies.tva_intra_com`, `created_at`, `updated_at`.
- **`typologie`** (`typology.py`, classe `Typologie`) : `id`, `type_name`, `role_id` → `roles` (équivalent « user_role » dans la spec).
- **`companies_bank_info`** : `id`, `company_id` (TVA), `iban_number`, `bic`, `bank_name`, `iban_proof`, `is_primary`, `company_payment_method_id` (nullable, FK vers `company_payment_methods`).
- **`company_payment_methods`** : `id`, `methode`, `user_id`, `company_id` (TVA), `companies_bank_info_id` (nullable).

### `companies` — changement majeur

- **PK** : `tva_intra_com` (`String(32)`) — **plus de `id` entier**.
- **Remplacements / ajouts** : `company_name` (à la place de l’ancien champ `role` texte sur la société), `phone_number`, `code_naf`, `email`, `condition_reglement`, `branche`, `extrait_kbis`, `cgv_accepted`, `website`, `description`, `logo`.
- Supprimé sur `companies` : `user_id`, `role`, `registration_number`, `vat_number` (la TVA est la PK).

### FK `company_id` (String)

Toutes les références à l’ancien `companies.id` (int) pointent vers **`companies.tva_intra_com`** : `addresses`, `company_translations`, `catalogs`, `catalog_items`, `services`, `shipping_rates`, `companies_users`, `companies_bank_info`, `company_payment_methods`.

### `users`

- `role_id` → `roles` (remplace `is_vendor`).
- `mobile_phone`, `fixe_phone` (remplace le champ unique `phone`).

### `user_profiles`

- `title` (civilité / titre).

### `addresses`

- `siret`, `intra_communal`.

### API / repos alignés

- Inscription **client** / **fournisseur** : payload avec `tva_intra_com`, `company_name` obligatoires ; réponse **`tva_intra_com`** (plus de champ `company_id` dans le JSON).
- ORM : attribut Python **`company_tva_intra_com`** sur les modèles liés à `companies` ; colonne SQL reste souvent nommée **`company_id`** (valeur = TVA, FK → `companies.tva_intra_com`).
- Métriques fournisseur : query **`tva_intra_com`** (plus `company_id`).
- **À faire** : migration Alembic + **données initiales** dans `roles` (`client`, `Fournisseur`, `admin`) pour que `role_id` soit renseigné.

---

## 2026-02-27 – Schéma Marketplace Urbanize v5 (remplacement complet)

Alignement des modèles Python sur le schéma décrit dans le fichier HTML (Mermaid ER diagram v5). **Anciennes tables CRM (tenant, deal, contact, document, carts, cart_items, etc.) supprimées** et remplacées par le schéma multilingue / catalogue / commandes / avis.

### Nouvelles tables (fichiers dans `backend/app/models/`)

| Fichier | Table SQL | Description |
|---------|-----------|-------------|
| `language.py` | `languages` | Langues (i18n) |
| `user.py` | `users` | Utilisateurs (email, password_hash, phone, is_vendor, is_active) |
| `user_profile.py` | `user_profiles` | Profil utilisateur (user_id, language_id, first_name, last_name) |
| `company.py` | `companies` | Sociétés (user_id, role, registration_number, vat_number, is_verified) |
| `company_translation.py` | `company_translations` | Traductions company (company_id, language_id, name, slug, description) |
| `address.py` | `addresses` | Adresses company (company_id, type, street, city, zip_code, state, country_code, lat, lng, is_primary) |
| `category.py` | `categories` | Catégories (parent_id, sort_order) |
| `category_translation.py` | `category_translations` | Traductions catégories |
| `image.py` | `images` | Table unifiée images (entity_type, entity_id, url, alt_text, sort_order, is_main) |
| `product.py` | `products` | Produits (category_id, product_type, reference_price, currency, sku, is_active) |
| `product_component.py` | `product_components` | Composants assemblage (parent_product_id, component_id, quantity, component_type) |
| `product_shipping.py` | `product_shipping` | Infos livraison produit (product_id, weight_kg, dimensions, volume_m3, freight_class) |
| `product_translation.py` | `product_translations` | Traductions produits (name, slug, description, meta_title, meta_description) |
| `catalog.py` | `catalogs` | Catalogues par company (company_id, name, description, is_active) |
| `catalog_item.py` | `catalog_items` | Lignes catalogue (catalog_id, product_id, company_id, custom_price, stock_quantity, is_available) |
| `shipping_rate.py` | `shipping_rates` | Grilles tarifaires livraison (company_id, carrier_name, zones, poids/volume, base_rate, rate_per_kg) |
| `service.py` | `services` | Services (company_id, category_id, reference_price, duration_unit/value, remote_available) |
| `service_translation.py` | `service_translations` | Traductions services |
| `order.py` | `orders` | Commandes (user_id, status, subtotal, tax_amount, shipping_amount, total_amount, currency) |
| `order_item.py` | `order_items` | Lignes commande (order_id, catalog_item_id, service_id, item_type, quantity, unit_price, shipping_cost, total_price) |
| `order_address.py` | `order_addresses` | Adresses commande (order_id, type, first_name, last_name, street, city, zip_code, country_code) |
| `payment.py` | `payments` | Paiements (order_id, provider, transaction_id, status, amount, paid_at) |
| `review.py` | `reviews` | Avis (user_id, product_id, service_id, rating, item_type, is_verified_purchase) |
| `review_translation.py` | `review_translations` | Traductions avis |

### Fichiers supprimés (ancien schéma CRM)

- `tenant.py`
- `contact.py`
- `deal.py`
- `document.py`
- `carts.py`
- `cart_items.py`
- `products.py` (ancien, remplacé par `product.py`)

### Relations principales

- **Users** → UserProfile (1-1), Company (0-1), Orders, Reviews  
- **Companies** → Addresses, CompanyTranslations, Catalogs, CatalogItems, Services, ShippingRates  
- **Categories** → parent/children (récurseif), CategoryTranslations, Products, Services  
- **Products** → Category, ProductTranslations, ProductShipping, CatalogItems, Reviews, ProductComponents (assemblage)  
- **Catalogs** → Company, CatalogItems  
- **CatalogItems** → Catalog, Product, Company, OrderItems  
- **Orders** → User, OrderItems, OrderAddresses, Payments  
- **OrderItems** → Order, CatalogItem (optionnel), Service (optionnel)  
- **Images** : pas de FK (entity_type + entity_id polymorphiques)

### Fichiers Python mis à jour hors models

- `app/models/__init__.py` : exports des nouveaux modèles uniquement.
- `app/repositories/metrics_repo.py` : requêtes basées sur Order, OrderItem, CatalogItem (plus de tenant/deal).
- `app/services/metrics.py` : `build_internal_metrics(db)` sans tenant, `build_supplier_metrics(db, company_id)`.
- `app/schemas/metrics.py` : `InternalMetrics` sans tenant_id/deals, `SupplierMetrics` avec company_id.
- `app/api/v1/endpoints/metrics.py` : GET `/metrics/internal` sans paramètre, GET `/metrics/supplier?company_id=...`.

### À faire côté Alembic

Le schéma v5 n’a plus de tables `tenants`, `deals`, `contacts`, `documents`, `carts`, `cart_items` et l’ancienne `products`. Selon ta stratégie :

1. **Nouvelle base** : appliquer une migration qui crée toutes les nouvelles tables.
2. **Base existante** : créer une révision qui supprime les anciennes tables et crée les nouvelles (ou faire une migration manuelle + `alembic revision --autogenerate` après coup).

Commandes typiques :

```bash
cd backend
python -m alembic revision --autogenerate -m "marketplace_urbanize_v5_schema"
python -m alembic upgrade head
```

Vérifier le script généré avant d’exécuter `upgrade head` (drops et creates).
