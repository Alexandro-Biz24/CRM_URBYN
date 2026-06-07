
DB cmd : 
- création d'une nouvelle tbale ou modification de colonne d'une tabe dans backend/app/models/..
- python -m alembic revision --autogenerate -m "add nom de la table ou de la modifie (message humain)" 
- python -m alembic upgrade head
- python -m alembic current

## Deploy Render

| Champ | Valeur |
|-------|--------|
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

⚠️ **Pas** `app.api:app` — l'application FastAPI est dans `app/main.py` → `app.main:app`.

Health check : `GET /health` — Swagger : `/docs`
