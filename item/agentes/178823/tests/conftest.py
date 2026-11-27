"""Fixtures de pruebas del agente 178823.

Las pruebas de integración crean una base limpia (`erp_item_178823_test`) con
item/schema/schema.sql + la extensión + los datos semilla. Si PostgreSQL no
está disponible se omiten y solo corren las pruebas unitarias.
"""

import os
import sys
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1]
ITEM_DIR = AGENT_DIR.parents[1]
sys.path.insert(0, str(AGENT_DIR))

TEST_DB = "erp_item_178823_test"
BASE = dict(host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            user=os.getenv("PGUSER", "postgres"), password=os.getenv("PGPASSWORD", "postgres"))
SQL_FILES = [ITEM_DIR / "schema" / "schema.sql",
             AGENT_DIR / "sql" / "01_extension_sentinel_178823.sql",
             AGENT_DIR / "sql" / "02_seed_sentinel_178823.sql"]


def _dsn(db):
    return " ".join(f"{k}={v}" for k, v in {**BASE, "dbname": db}.items())


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        admin = psycopg2.connect(_dsn("postgres"))
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL no disponible: {exc}")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {TEST_DB}")
    admin.close()
    conn = psycopg2.connect(_dsn(TEST_DB))
    conn.autocommit = True
    with conn.cursor() as cur:
        for f in SQL_FILES:
            cur.execute(f.read_text(encoding="utf-8"))
    conn.close()
    monkeypatch.setenv("PG_DSN", _dsn(TEST_DB))
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)
    return tmp_path


@pytest.fixture()
def agent(fresh_db):
    from sku_sentinel.agent import SkuSentinelAgent
    from sku_sentinel.repositories import AuditLog, PgGraph, PgRepository
    repo = PgRepository()
    ag = SkuSentinelAgent(repo, PgGraph(repo), AuditLog(fresh_db / "decisiones.jsonl"))
    yield ag
    repo.close()
