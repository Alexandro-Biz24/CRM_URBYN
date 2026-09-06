from __future__ import annotations

import logging
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


def _with_ipv4_hostaddr(url: str) -> str:
    """Force IPv4 for Neon/Postgres hosts.

    Sur macOS, la résolution DNS renvoie souvent l'IPv6 en premier ; la
    connexion TCP IPv6 peut alors rester bloquée ~30s avant fallback.
    `hostaddr` force l'IP v4 tout en gardant le hostname pour le TLS/SNI.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return url

    qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if qs.get("hostaddr"):
        return url

    try:
        infos = socket.getaddrinfo(host, parsed.port or 5432, socket.AF_INET, socket.SOCK_STREAM)
        ipv4 = infos[0][4][0] if infos else None
    except OSError as exc:
        logger.warning("Impossible de résoudre IPv4 pour %s: %s", host, exc)
        return url

    if not ipv4:
        return url

    qs["hostaddr"] = ipv4
    return urlunparse(parsed._replace(query=urlencode(qs)))


_db_url = _with_ipv4_hostaddr(settings.DATABASE_URL)
engine = create_engine(
    _db_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
