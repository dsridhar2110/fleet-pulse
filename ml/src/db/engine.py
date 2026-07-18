"""Neon Postgres connection + schema bootstrap.

The connection string is read from the DATABASE_URL environment variable (the
Neon *pooled* string). Nothing here hard-codes a credential — locally it comes
from `ml/.env`; in CI it comes from a GitHub Actions secret.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def _load_dotenv() -> None:
    """Best-effort load of ml/.env so local runs need no manual export."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ModuleNotFoundError:  # tiny fallback parser if python-dotenv absent
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_url() -> str:
    """Return a SQLAlchemy-compatible Postgres URL from DATABASE_URL."""
    _load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Put the Neon *pooled* connection string in "
            "ml/.env (DATABASE_URL=postgresql://...-pooler...neon.tech/db?sslmode=require)."
        )
    # Neon/Heroku sometimes emit the postgres:// alias; SQLAlchemy wants postgresql://.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def get_engine(**kwargs) -> Engine:
    """Create a pooled SQLAlchemy engine. `pool_pre_ping` survives Neon's idle sleep."""
    return create_engine(get_url(), pool_pre_ping=True, future=True, **kwargs)


def init_schema(engine: Engine | None = None) -> None:
    """Run schema.sql (idempotent). Creates every table if absent."""
    engine = engine or get_engine()
    ddl = SCHEMA_SQL.read_text()
    with engine.begin() as conn:
        conn.exec_driver_sql(ddl)  # psycopg2 executes the whole multi-statement script


def ping(engine: Engine | None = None) -> str:
    """Return the Postgres server version — a one-line connectivity check."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        return conn.execute(text("select version()")).scalar_one()


if __name__ == "__main__":
    # `python -m db.engine` → verify connectivity and create the schema.
    eng = get_engine()
    print("connected:", ping(eng)[:60], "...")
    init_schema(eng)
    with eng.connect() as c:
        tables = c.execute(text(
            "select table_name from information_schema.tables "
            "where table_schema='public' order by table_name")).scalars().all()
    print(f"schema ready — {len(tables)} tables:", ", ".join(tables))
