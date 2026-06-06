"""
Logique métier pour l'inscription client : contrôles d'unicité puis création du compte.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import clients_repo
from app.schemas.clients import ClientAccount, ClientAccountCreate


@dataclass
class ClientConflictError(Exception):
    """Conflit à l'inscription (email ou TVA intracom déjà utilisée)."""
    field: str
    message: str


def register_client(
    db: Session,
    data: ClientAccountCreate,
) -> ClientAccount:
    """
    Vérifie les contraintes (email unique, tva_intra_com unique)
    puis crée le compte client.
    """
    existing_user = clients_repo.get_user_by_email(db=db, email=str(data.email))
    if existing_user is not None:
        raise ClientConflictError(
            field="email",
            message="Un utilisateur avec cet email existe déjà.",
        )

    conflict = clients_repo.get_company_by_tva_intra_com(
        db=db, tva=data.tva_intra_com.strip()
    )
    if conflict is not None:
        raise ClientConflictError(
            field="tva_intra_com",
            message="Une société avec cette TVA intracommunautaire existe déjà.",
        )

    user, company = clients_repo.create_client_account(db=db, data=data)
    db.commit()
    db.refresh(user)
    db.refresh(company)

    return ClientAccount(
        user_id=user.id,
        tva_intra_com=company.tva_intra_com,
        email=user.email,
        role_id=user.role_id,
        is_active=user.is_active,
        is_verified=company.is_verified,
    )
