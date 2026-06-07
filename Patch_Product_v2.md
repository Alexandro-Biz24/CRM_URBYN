# Patch_Product_v2

> Brief pour Cursor / dev API & front — changements **DB + modèles SQLAlchemy** (migration Alembic `e7f8a9b0c1d2`, parent `d1e2f3a4b5c6`).

---

## Contexte

Les **catalogues** sont centraux et **partagés** (plus de `company_id` sur `catalogs`).  
Un **produit** appartient à une **société** (`companies_id`) et peut être listé dans **plusieurs catalogues**.  
Les **specs produit** ne vivent plus en colonnes fixes sur `products` : elles passent par un système d’**attributs** (obligatoires vs libres).

**Prix** (hors scope de ce patch mais toujours valide) : `product_price_history` — append-only, prix affiché = dernière ligne par `product_id` (`recorded_at` DESC).

---

## Migration

```bash
cd backend && source .venv/bin/activate && python -m alembic upgrade head
```

Révision cible : **`e7f8a9b0c1d2`**.

---

## Table `products` — état actuel

| Colonne SQL | Attribut ORM | Notes |
|-------------|--------------|-------|
| `id` | `id` | PK |
| `ADMIN_SKU` | `admin_sku` | **unique**, généré côté app (`ADM-00000001`) |
| `Client_sku` | `client_sku` | SKU libre fournisseur, **sans contrainte d’unicité** |
| `companies_id` | `company_tva_intra_com` | FK → `companies.tva_intra_com` |
| `product_name` | `product_name` | ex-`product_type` |
| `is_active` | `is_active` | |
| `created_at` / `updated_at` | idem | |

### Supprimé (ne plus utiliser en API)

- `catalog_ref` → remplacé par **`catalog_products`**
- `quantity` → stock retiré du modèle produit
- `product_type` → renommé **`product_name`**
- Toutes colonnes métier directes : `teinte`, `longueur`, `largeur`, `hauteur`, `volume`, `poids_net`, `gamme`, `type_bois`, etc.

---

## Nouvelles tables

### 1. `catalog_products` — produit ↔ catalogue (N–N)

| Colonne | FK | Contrainte |
|---------|-----|------------|
| `catalog_id` | `catalogs.id` CASCADE | PK composite |
| `product_id` | `products.id` CASCADE | PK composite |

**Requêtes types :**

```sql
-- Produits d'un catalogue
SELECT p.* FROM products p
JOIN catalog_products cp ON cp.product_id = p.id
WHERE cp.catalog_id = :catalog_id;

-- Catalogues d'un produit
SELECT c.* FROM catalogs c
JOIN catalog_products cp ON cp.catalog_id = c.id
WHERE cp.product_id = :product_id;
```

**Règle métier :** à la création / édition produit, insérer ou synchroniser les lignes `catalog_products`. Un produit **doit** être dans au moins un catalogue (logique app, pas contrainte SQL).

---

### 2. `catalog_links` — similarité directionnelle entre catalogues

| Colonne | FK | Contrainte |
|---------|-----|------------|
| `id` | PK | |
| `from_catalog_id` | `catalogs.id` CASCADE | unique `(from_catalog_id, to_catalog_id)` |
| `to_catalog_id` | `catalogs.id` CASCADE | **le sens compte** : A→B ≠ B→A |
| `created_at` | | |

Historique cumulatif des paires déclarées par les fournisseurs (pas de suppression implicite).

---

### 3. Attributs produit — double système

```
catalogs
  └── catalog_attribute_definitions     ← schéma ADMIN (noms obligatoires)
        └── product_mandatory_attribute_values   ← valeurs par produit

products
  └── product_attribut                  ← attributs LIBRES fournisseur (inchangé)
```

#### `catalog_attribute_definitions` (schéma admin)

| Colonne | Notes |
|---------|-------|
| `id` | PK |
| `catalog_id` | FK `catalogs.id` CASCADE |
| `attribute_name` | ex. `poids`, `hauteur`, `largeur` — unique par catalogue |
| `created_at`, `updated_at` | |

**Pas de `value` ici** — ce sont les champs **obligatoires** que tout produit du catalogue doit remplir.

CRUD : à la création / modification d’un **catalogue** (interface admin).

#### `product_mandatory_attribute_values` (valeurs obligatoires)

| Colonne | FK | Contrainte |
|---------|-----|------------|
| `id` | PK | |
| `product_id` | `products.id` CASCADE | unique `(product_id, catalog_attribute_definition_id)` |
| `catalog_attribute_definition_id` | `catalog_attribute_definitions.id` CASCADE | |
| `value` | TEXT, saisie libre | validation métier côté app |
| `created_at`, `updated_at` | | |

**Règle métier :** pour chaque définition du catalogue auquel le produit est rattaché, le fournisseur doit fournir une valeur (à valider en API avant save).

**Requête — attributs obligatoires d’un produit avec noms :**

```sql
SELECT cad.attribute_name, pmav.value
FROM product_mandatory_attribute_values pmav
JOIN catalog_attribute_definitions cad ON cad.id = pmav.catalog_attribute_definition_id
WHERE pmav.product_id = :product_id;
```

#### `product_attribut` (sur mesure fournisseur — **inchangé**)

| Colonne | Notes |
|---------|-------|
| `product_id` | FK products |
| `name`, `value` | clé-valeur libre, **non** liée au schéma catalogue |
| `created_at`, `updated_at` | |

Optionnel, spécifique au produit / fournisseur. Ne pas confondre avec les attributs obligatoires.

---

## Modèles SQLAlchemy (`backend/app/models/`)

| Fichier | Classe | Table |
|---------|--------|-------|
| `product.py` | `Product` | `products` |
| `catalog_product.py` | `CatalogProduct` | `catalog_products` |
| `catalog_link.py` | `CatalogLink` | `catalog_links` |
| `catalog_attribute_definition.py` | `CatalogAttributeDefinition` | `catalog_attribute_definitions` |
| `product_mandatory_attribute_value.py` | `ProductMandatoryAttributeValue` | `product_mandatory_attribute_values` |
| `product_attribut.py` | `ProductAttribut` | `product_attribut` |

Relations clés sur `Product` :

- `catalog_products` → listes de catalogues
- `mandatory_attribute_values` → valeurs admin
- `attributes` → attributs libres (`ProductAttribut`)
- `price_history` → série de prix

---

## `product_order` (commandes — rappel)

Toujours : `catalog_id` **figé** au moment de la commande (snapshot), + `product_id`, prix, qty.  
Ne pas déduire le catalogue depuis `catalog_products` pour une ligne commande existante.

---

## Breaking changes API / front (à adapter)

| Ancien | Nouveau |
|--------|---------|
| `product.catalog_ref` | `catalog_products` (liste de `catalog_id`) |
| `product.product_type` | `product.product_name` |
| `product.quantity` | supprimé |
| champs `teinte`, `longueur`, … sur product | `product_mandatory_attribute_values` + `product_attribut` |
| `reference_price` / `currency` sur product | `product_price_history` (dernier `recorded_at`) |
| un seul catalogue par produit | **plusieurs** via `catalog_products` |

Endpoints `supplier_portal`, `suppliers_offers_v2`, `client_orders_v2`, `metrics` **non alignés** avec ce patch tant qu’ils n’ont pas été refaits.

---

## Flux métier attendu (API à implémenter)

### Admin — catalogue

1. CRUD `catalogs` (+ `parent_id` hiérarchie).
2. CRUD `catalog_attribute_definitions` pour ce catalogue (`attribute_name`).

### Fournisseur — produit

1. Créer `Product` (`product_name`, `client_sku`, `companies_id`, …).
2. Lier à un ou plusieurs catalogues → `catalog_products`.
3. Pour **chaque** `catalog_attribute_definitions` des catalogues liés → upsert `product_mandatory_attribute_values`.
4. Optionnel : ajouter `product_attribut` (libres).
5. Prix → `INSERT` dans `product_price_history` (jamais de prix sur `products`).

### Fournisseur — similarité catalogues

- `INSERT` dans `catalog_links` (`from_catalog_id`, `to_catalog_id`) — sens unique.

---

## Diagramme

```mermaid
erDiagram
    catalogs ||--o{ catalog_products : contains
    products ||--o{ catalog_products : listed_in
    catalogs ||--o{ catalog_attribute_definitions : defines
    catalog_attribute_definitions ||--o{ product_mandatory_attribute_values : typed_by
    products ||--o{ product_mandatory_attribute_values : has
    products ||--o{ product_attribut : custom
    products ||--o{ product_price_history : priced
    catalogs ||--o{ catalog_links : from
    catalogs ||--o{ catalog_links : to
    companies ||--o{ products : sells
```

---

## Fichiers de référence

- Migration : `backend/alembic/versions/e7f8a9b0c1d2_catalog_n_n_mandatory_attrs.py`
- Refonte précédente : `d1e2f3a4b5c6_refonte_catalog_centrique.py`
- Spec produit / roadmap : `roadmap.md` (l.601+)
