


DB cmd : 
- création d'une nouvelle tbale ou modification de colonne d'une tabe dans backend/app/models/..
- python -m alembic revision --autogenerate -m "add nom de la table ou de la modifie (message humain)" 
- python -m alembic upgrade head
- python -m alembic current