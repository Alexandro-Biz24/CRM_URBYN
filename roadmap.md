session.py

Crée :

engine

SessionLocal

🔹 models/

Chaque fichier = une table SQL.

Les modèles définissent :

colonnes

types

relations

contraintes

Exemples :

tenant

user

company

deal

order

cart

product

Alembic utilise Base.metadata pour générer les migrations.

🔹 schemas/

Modèles Pydantic pour l’API.

Important :
Modèle SQLAlchemy ≠ Schéma API

Les schemas servent à :

Valider les inputs

Structurer les outputs

Exemples :

DealCreate

DealRead

DealUpdate

🔹 repositories/

Contiennent uniquement les requêtes base de données.

Exemple :

get_deal_by_id()

list_deals()

create_deal()

Aucune logique métier ici.

🔹 services/

Contiennent la logique métier.

Exemples :

transitions.py → gérer les changements de statut

rbac.py → vérifier permissions

documents.py → génération PDF

workflows.py → déclenchement n8n

Les services utilisent les repositories.

🔹 api/

Contient les endpoints REST.

Structure :

api/v1/endpoints/

Exemples :

auth

users

deals

orders

metrics

Les endpoints :

appellent les services

retournent des schemas

Ils ne contiennent pas de logique métier complexe.

🔹 utils/

Fonctions utilitaires :

génération d’ID

gestion du temps

helpers techniques

🔁 4. Alembic – Gestion des migrations

Structure :

alembic/
  env.py
  script.py.mako
  versions/

Processus :

Modifier un modèle

Générer migration :

alembic revision --autogenerate -m "message"

Appliquer :

alembic upgrade head

La table alembic_version garde l’historique.

🎨 5. Frontend

Le frontend :

Appelle le backend

Affiche les données

Dessine les graphiques

Gère l’authentification

Il ne contient aucune logique métier.

Il consomme l’API.

🔁 6. n8n – Automatisation

Exemples :

Quand un deal est SIGNED
→ Appel webhook
→ Génération PDF
→ Envoi email

n8n exécute des workflows automatisés.

🌍 7. Multi-tenant

Chaque table contient :

tenant_id

Cela permet :

Une seule base

Plusieurs entreprises

Isolation logique

🔄 8. Flux métier complet

User crée un Cart

Ajoute des produits

Valide le Cart → devient Deal

Deal signé → devient Order

Order completed → revenu comptabilisé

Ensuite :

Le dashboard agrège les données.

📊 9. Dashboard

Endpoints typiques :

GET /metrics/internal

GET /metrics/supplier

Ils renvoient :

total revenue

revenue mensuel

nombre de deals

top fournisseurs

statistiques globales

Un endpoint = toutes les données nécessaires au frontend.

🧪 10. Tests

Structure :

tests/
  test_auth.py
  test_rbac.py
  test_transitions.py

On teste :

login

permissions

transitions métier

🚀 11. Processus pour ajouter une feature

Toujours suivre cet ordre :

Modifier modèle

Générer migration

Appliquer migration

Ajouter repository

Ajouter service

Ajouter endpoint

Ajouter schema

Brancher frontend

🧱 12. Ce qui est déjà fait

Base SQL opérationnelle

Multi-tenant actif

Alembic stable

Modèles propres

Architecture définie

🎯 13. Prochaine étape

Développer dans cet ordre :

CRUD products

CRUD carts

cart → deal workflow

deal → order workflow

endpoints metrics

dashboards frontend

Quand cela fonctionne :

Le CRM est vivant.

🧠 Résumé ultra simple

Backend = cerveau
Frontend = interface
Database = mémoire
Alembic = historien
Repositories = accès mémoire
Services = règles métier
API = porte d’entrée
n8n = robot automatique

Ce projet n’est pas une simple API.

C’est une architecture CRM modulaire prête à évoluer, s’étendre et scaler


crm-suite/
  README.md
  .env.example
  docker-compose.yml              # optionnel (postgres local, redis, etc.)

  backend/
    pyproject.toml
    alembic.ini
    alembic/
      env.py
      script.py.mako
      versions/
        0001_init.py

    app/
      __init__.py
      main.py                     # create_app + include routers
      core/
        config.py                 # settings (.env)
        security.py               # hash pwd, JWT
        deps.py                   # deps FastAPI (get_db, current_user)
        logging.py
      db/
        session.py                # engine + sessionmaker
        base.py                   # Base SQLAlchemy
      models/
        tenant.py
        user.py
        company.py
        contact.py
        deal.py
        order.py
        document.py
        audit_event.py
      schemas/                    # Pydantic (input/output)
        auth.py
        user.py
        deal.py
        order.py
        metrics.py
      repositories/               # accès DB (queries)
        deal_repo.py
        order_repo.py
        metrics_repo.py
      services/                   # logique métier (RBAC, transitions, pdf trigger)
        rbac.py
        transitions.py
        documents.py
        workflows.py              # client n8n (webhook interne)
      api/
        __init__.py
        v1/
          router.py
          endpoints/
            auth.py
            users.py
            deals.py
            orders.py
            documents.py
            metrics.py
      utils/
        ids.py
        time.py

    tests/
      test_auth.py
      test_rbac.py
      test_transitions.py

  frontend/
    package.json
    src/
      app/
      pages/
      components/
      api/                        # client fetch vers backend
      charts/                     # recharts/chartjs
      auth/

  n8n/
    workflows/
      quote_generate.json
      reminders_cron.json

  infra/
    nginx/
    terraform/                    # optionnel




---

# 🧠 3. Comprendre le Backend

Le backend est le **cerveau du système**.

Il est construit avec :

- FastAPI
- SQLAlchemy
- Alembic
- Pydantic
- PostgreSQL

---

## 🔹 main.py

Point d’entrée de l’application.

Responsabilités :

- Créer l’app FastAPI
- Inclure les routers
- Initialiser middleware
- Démarrer l’API

---

## 🔹 core/

Contient les briques fondamentales.

### config.py
- Charge les variables `.env`
- Configure DATABASE_URL, JWT_SECRET, etc.

### security.py
- Hash password
- Génération JWT
- Vérification token

### deps.py
- get_db()
- get_current_user()
- dépendances FastAPI

---

## 🔹 db/

### base.py
Déclare la base SQLAlchemy :

```python
Base = declarative_base()


# 🧠 Architecture Backend & Système CRM – Documentation Technique

---

## 🔹 db/session.py

`session.py` crée :

- `engine` → connexion à la base PostgreSQL
- `SessionLocal` → factory pour créer des sessions DB

Il permet à l’API d’ouvrir et fermer proprement des connexions à la base.

---

## 🔹 models/

Chaque fichier correspond à **une table SQL**.

Les modèles définissent :

- Colonnes
- Types
- Relations
- Contraintes

Exemples de modèles :

- tenant
- user
- company
- deal
- order
- cart
- product

Alembic utilise `Base.metadata` pour générer automatiquement les migrations à partir de ces modèles.

---

## 🔹 schemas/

Les schemas sont des modèles **Pydantic** utilisés par l’API.

Important :

Modèle SQLAlchemy ≠ Schéma API

Les schemas servent à :

- Valider les inputs (requêtes entrantes)
- Structurer les outputs (réponses API)

Exemples :

- DealCreate
- DealRead
- DealUpdate

Ils protègent l’API et définissent ce qui est exposé ou accepté.

---

## 🔹 repositories/

Les repositories contiennent uniquement les **requêtes base de données**.

Exemples :

- `get_deal_by_id()`
- `list_deals()`
- `create_deal()`

Ils ne contiennent **aucune logique métier**.

Ils servent uniquement à accéder aux données.

---

## 🔹 services/

Les services contiennent la **logique métier**.

Exemples :

- `transitions.py` → gérer les changements de statut
- `rbac.py` → vérifier permissions
- `documents.py` → génération PDF
- `workflows.py` → déclenchement n8n

Les services utilisent les repositories.

Ils orchestrent les règles métier du CRM.

---

## 🔹 api/

Contient les endpoints REST.

Structure  DEMANDÉ :


{ role : CLIENT/ADMIN/FOURNISSEUR
demande : description du besoin en output pour le front 
autre : précision exceptionnel mais aps obligatoire 
}










Gestion catalogs pas de suppression 

Table intermedaire multi cat par product et multi produit par cat 

Accompagnement des fournisseur sur le mapping des catalog pour un fournisseur, on fait de historique de tt les connexion inter catalog de la table de liaison 

associé par catalog les attribu obligatoire 


pour les produit :


suppresison de stock 
devise par defaut 
pouvoir modifier le sku_client 


ok 

1) actuellemnt la notion de catalog récurssif avec parent id pour faire des sous catalogs etc c'est trop bien et on peux associer un produit a un catalog odnc les catalog peuvent contenir une multitude produit. 

finalement j'aurais besoin que les produits puissent etre aussi reference dans plusieur catalogs (typiquement deux famille proche ou en prevision de produit hybirde quoi. mais lacomme ça avec juste la table produit et la table catalog je vois pas comment faire est ce qu'il fuat une table intermediaire qui sert de reference ? pour que un catalog liste plusieurs produit et un meme produit soit dans plusieurs catalogue  ? fait moi une ou des proposition pour qu eça soit simple pragmatique et rapide a la reuqete 

2) par conséquent et dans un objectif de faire des propositions de lien d'un produit placé das un catalog avec d'autre catalog 'similaire' j'aurais besoin d'une table meme pas liée au reste de la data base qui juste referencera de maniere UNIQUE les paire de catalog qui on été liée par les fournisseur tt au long de la vie de la DB. et dans un sens unique ça sera un champs from et un champ to 

genre 'from massif beton to Lestage'donc si jamais il y a la paire from lestage to massif beton elle ets bien differnete le sens est IMPORTANT 


3) au niveau de la table produit la logique des attribut separe et modifiebale a la guise c'est TOP mais finalment sur la table product directement, il y a un soucis je vais pas reference 100 paramtere d eprduit a la main. surtotu que chaque ctaalog va avoir des parametre qui leur seront propre donc je devrais pouvoir associé par catalogue des parametre de produit qui leur soit propre. 

donc d'une maniere ou d'une autre il faut que si je suis dans le massif beton et que je créer un produit je vais ecrie dans des champs "poids" "hauteur" "largeur" par exemple, mais ces champs la je pense pas qu'il doivent exister dans la able produit directement, il me faut une table a part je pense que je peux modifier direct via mon interface, par modifier j'entend je créée en tant qu'admin un nouveau catalog je veux en meme temps definir quel sont les attribut/parmaetre des produit de ce catalog que j'autorise a saisir. 
Donc peut etre juste dans la table catalog rajouter un referenicel à une nouvelle table  ou si pas ebsoin juste cette nouvelle table  qui reference justement à partir de l'id d'un catalog dans un champs un nom d'attribut dans un autre champs et un champs de valeur de l'attribut 

et ça se ser gérer direct par api via l'interface donc je peux pas savoir a l'avance si le parametre qui sera créé pour un produti d'un catalog sera en une valeur a chosiir parmis une liste  un str ou un int à la limite c'ets du detail et je ferai un truc full char si il fuat mais si il peut y avoir gestion dynamique de ça sachant que pour chaque attribut de chaque catalog je sai spas si c'est possible dans le champs valeur d'avori different type pour moi non. Donc on laisse de la siasi libre et l apartie restrictive sera gérer dnas le knowledge de l'app. Donc fait moi juste cette nouvellle table liée à catalog pour la  3) qui me permet donc de créer des attribu liée a un catalog direct et efface tout les champs de product SAUF : [catalog_ref
ADMIN_SKU
Client_sku
created_at
updated_at
product_type
is_active
companies_id]

bien entendu. et aussi renomme product_type par product_name stp 


