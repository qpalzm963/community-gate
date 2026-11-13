from __future__ import annotations

import ssl
from collections.abc import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_config


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _set_sqlite_pragma(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def normalize_db_url(raw_url: str) -> tuple[str, dict]:
    """轉換外部資料庫連線字串（例如 aiBorn 的 mysql://...?sslaccept=accept_invalid_certs）。"""
    url = raw_url.strip()
    if url.startswith("mysql://"):
        url = "mysql+pymysql://" + url[len("mysql://") :]
    elif url.startswith("mariadb://"):
        url = "mysql+pymysql://" + url[len("mariadb://") :]

    if url.startswith("sqlite"):
        return url, {"check_same_thread": False}

    if url.startswith("mysql+pymysql://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        ssl_accept = query.pop("sslaccept", "").lower()
        ssl_mode = (query.pop("ssl-mode", "") or query.pop("ssl_mode", "")).lower()
        query.pop("connection_limit", None)
        query.pop("pool_timeout", None)
        clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

        connect_args: dict = {}
        if ssl_accept or ssl_mode:
            ctx = ssl.create_default_context()
            if ssl_accept in ("accept_invalid_certs", "true", "1") or ssl_mode in ("preferred", "required", "skip-verify"):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx
        return clean_url, connect_args

    return url, {}


def init_engine(url: str | None = None) -> Engine:
    """建立（或重建）資料庫 engine。測試可傳入自訂 URL。"""
    global _engine, _SessionLocal
    if url is None:
        cfg = get_config()
        cfg.ensure_dirs()
        url = cfg.database_url or f"sqlite:///{cfg.db_path}"

    sa_url, connect_args = normalize_db_url(url)
    is_sqlite = sa_url.startswith("sqlite")
    kwargs: dict = {"connect_args": connect_args}
    if not is_sqlite:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800

    _engine = create_engine(sa_url, **kwargs)
    if is_sqlite:
        event.listen(_engine, "connect", _set_sqlite_pragma)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def SessionLocal() -> Session:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
