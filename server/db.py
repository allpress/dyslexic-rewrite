"""Postgres access: a small connection pool and an in-order SQL migration runner."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite")

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True)
    return _pool


@contextmanager
def conn():
    with pool().connection() as c:
        yield c


def migrate() -> list[str]:
    """Apply server/migrations/*.sql that have not been applied yet. Returns names applied."""
    mig_dir = Path(__file__).parent / "migrations"
    applied = []
    with conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        done = {r["name"] for r in c.execute("SELECT name FROM schema_migrations").fetchall()}
        for path in sorted(mig_dir.glob("*.sql")):
            if path.name in done:
                continue
            c.execute(path.read_text(encoding="utf-8"))
            c.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
        c.commit()
    return applied


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


__all__ = ["conn", "migrate", "close", "psycopg"]
