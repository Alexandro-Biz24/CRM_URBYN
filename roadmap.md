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