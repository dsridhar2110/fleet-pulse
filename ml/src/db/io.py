"""Fast bulk writes to Postgres via psycopg2 execute_values.

Kept deliberately small: batched appends for the fact tables, a JSONB-aware
upsert for `machine_state`, and a key/value setter for `world_meta`.
"""

from __future__ import annotations

import json

from psycopg2.extras import execute_values
from sqlalchemy.engine import Engine


def insert_rows(
    engine: Engine, table: str, columns: list[str], rows: list[tuple],
    jsonb_cols: tuple[str, ...] = (), page_size: int = 5000,
) -> int:
    """Batched INSERT. `rows` are tuples in `columns` order; JSONB cols carry
    already-serialised JSON strings."""
    if not rows:
        return 0
    cols = ", ".join(columns)
    template = "(" + ", ".join(
        f"%s::jsonb" if c in jsonb_cols else "%s" for c in columns) + ")"
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            execute_values(
                cur, f"INSERT INTO {table} ({cols}) VALUES %s",
                rows, template=template, page_size=page_size)
        raw.commit()
    finally:
        raw.close()
    return len(rows)


def upsert_machine_state(engine: Engine, machine_id: str, as_of_date, state: dict) -> None:
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(
                "INSERT INTO machine_state (machine_id, as_of_date, state) "
                "VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (machine_id) DO UPDATE SET "
                "as_of_date = EXCLUDED.as_of_date, state = EXCLUDED.state, updated_at = now()",
                (machine_id, as_of_date, json.dumps(state)))
        raw.commit()
    finally:
        raw.close()


def upsert_machine_states(engine: Engine, items: list[tuple], page_size: int = 500) -> int:
    """Bulk upsert. `items` = [(machine_id, as_of_date, state_dict), ...]."""
    if not items:
        return 0
    rows = [(m, d, json.dumps(s)) for m, d, s in items]
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO machine_state (machine_id, as_of_date, state) VALUES %s "
                "ON CONFLICT (machine_id) DO UPDATE SET "
                "as_of_date = EXCLUDED.as_of_date, state = EXCLUDED.state, updated_at = now()",
                rows, template="(%s, %s, %s::jsonb)", page_size=page_size)
        raw.commit()
    finally:
        raw.close()
    return len(rows)


def set_world_meta(engine: Engine, key: str, value: dict) -> None:
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(
                "INSERT INTO world_meta (key, value) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (key, json.dumps(value)))
        raw.commit()
    finally:
        raw.close()


def truncate_all(engine: Engine) -> None:
    """Wipe every data table (fresh backfill). Order respects FKs via CASCADE."""
    tables = [
        "governance_actions", "evolution_log", "model_versions",
        "impact_daily", "decisions", "predictions",
        "tickets", "maintenance", "failures", "error_events", "telemetry_daily",
        "machine_state", "machines", "customers", "world_meta",
    ]
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
        raw.commit()
    finally:
        raw.close()
