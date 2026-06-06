from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import admin_catalog_repo as repo
from app.schemas.admin import (
    AdminCatalogDetail,
    AdminCatalogNode,
    AdminCatalogTreeResponse,
    AdminCatalogUpdate,
    AdminCatalogWrite,
    AdminLoginResponse,
)


class AdminError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def login(login: str, password: str) -> AdminLoginResponse:
    if not settings.admin_configured:
        raise AdminError(
            "admin_not_configured",
            "Identifiants admin non configurés (ADMIN_ID / ADMIN_PWD).",
        )
    ok_login = secrets.compare_digest(login.strip(), settings.admin_id)
    ok_pwd = secrets.compare_digest(password, settings.admin_pwd)
    if not (ok_login and ok_pwd):
        raise AdminError("invalid_credentials", "Identifiant ou mot de passe incorrect.")
    from app.core.admin_auth import create_admin_token

    token, exp = create_admin_token()
    return AdminLoginResponse(token=token, expires_at=exp)


def _build_tree(
    db: Session,
    catalogs: list,
    parent_id: int | None,
) -> list[AdminCatalogNode]:
    nodes: list[AdminCatalogNode] = []
    for c in catalogs:
        is_root = c.parent_id is None or c.parent_id == c.id
        if parent_id is None:
            if not is_root:
                continue
        elif not (c.parent_id == parent_id and c.id != parent_id):
            continue
        nodes.append(
            AdminCatalogNode(
                id=c.id,
                name=c.name,
                description=c.description,
                is_active=c.is_active,
                parent_id=c.parent_id,
                child_count=repo.count_children(db, c.id),
                product_count=repo.count_products(db, c.id),
                children=_build_tree(db, catalogs, c.id),
            )
        )
    nodes.sort(key=lambda n: (n.name or "").lower())
    return nodes


def get_catalog_tree(db: Session) -> AdminCatalogTreeResponse:
    catalogs = repo.list_all_catalogs(db)
    roots = _build_tree(db, catalogs, None)
    return AdminCatalogTreeResponse(roots=roots, total=len(catalogs))


def get_catalog_detail(db: Session, catalog_id: int) -> AdminCatalogDetail:
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise AdminError("not_found", "Catalogue introuvable.")
    return AdminCatalogDetail(
        id=c.id,
        name=c.name,
        description=c.description,
        is_active=c.is_active,
        parent_id=c.parent_id,
        child_count=repo.count_children(db, c.id),
        product_count=repo.count_products(db, c.id),
        breadcrumb=repo.get_breadcrumb(db, c),
    )


def create_catalog(db: Session, data: AdminCatalogWrite) -> AdminCatalogDetail:
    try:
        c = repo.create_catalog(db, data)
        db.commit()
        db.refresh(c)
    except ValueError as exc:
        db.rollback()
        if str(exc) == "parent_not_found":
            raise AdminError("parent_not_found", "Catalogue parent introuvable.") from exc
        raise
    return get_catalog_detail(db, c.id)


def update_catalog(
    db: Session, catalog_id: int, data: AdminCatalogUpdate
) -> AdminCatalogDetail:
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise AdminError("not_found", "Catalogue introuvable.")
    repo.update_catalog(db, c, data)
    db.commit()
    db.refresh(c)
    return get_catalog_detail(db, c.id)


def delete_catalog(db: Session, catalog_id: int) -> None:
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise AdminError("not_found", "Catalogue introuvable.")
    try:
        repo.delete_catalog(db, catalog_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        code = str(exc)
        if code == "has_children":
            raise AdminError(
                "has_children",
                "Supprimez d'abord tous les sous-catalogues.",
            ) from exc
        if code == "has_orders":
            raise AdminError(
                "has_orders",
                "Ce catalogue est lié à des commandes et ne peut pas être supprimé.",
            ) from exc
        raise
