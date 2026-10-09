"""
Live-database fixtures for the connector integration tests.

Each backend runs only when its DSN is set (otherwise its tests are skipped):

    docker compose -f tests/integration/docker-compose.yml up -d --wait
    export DDL_LINEAGE_TEST_PG=postgresql://lineage:lineage@127.0.0.1:55432/lineage_test
    export DDL_LINEAGE_TEST_MYSQL=mysql://root:lineage@127.0.0.1:53306/lineage_it
    python -m pytest tests/integration

Loading a fixture recreates only its own schemas/databases (lineage_it,
lineage_it_noise), so pointing a DSN at a shared server does not touch other data.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

from ddl_lineage.parser import _remove_comments, _split_statements

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(ROOT / "web" / "backend"))


@dataclass(frozen=True)
class Backend:
    name: str
    env: str
    fixture: str
    default_port: int


BACKENDS = {
    "postgresql": Backend("postgresql", "DDL_LINEAGE_TEST_PG", "postgres_lineage.sql", 5432),
    "mysql": Backend("mysql", "DDL_LINEAGE_TEST_MYSQL", "mysql_lineage.sql", 3306),
}


def _config(backend: Backend, dsn: str) -> dict:
    url = urlparse(dsn)
    config = {
        "type": backend.name,
        "host": url.hostname,
        "port": url.port or backend.default_port,
        "username": unquote(url.username or ""),
        "password": unquote(url.password or ""),
    }
    if backend.name == "postgresql":
        config.update(database=url.path.lstrip("/"), schema="lineage_it")
    else:
        config.update(database="lineage_it")
    return config


def _load_postgresql(config: dict, sql: str) -> None:
    import psycopg2

    conn = psycopg2.connect(
        host=config["host"], port=config["port"], dbname=config["database"],
        user=config["username"], password=config["password"],
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()


def _load_mysql(config: dict, sql: str) -> None:
    import pymysql

    conn = pymysql.connect(
        host=config["host"], port=config["port"],
        user=config["username"], password=config["password"], autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            # No DELIMITER support in the driver: split BEGIN … END-aware ourselves
            for stmt in _split_statements(_remove_comments(sql)):
                if stmt.strip():
                    cur.execute(stmt)
    finally:
        conn.close()


@pytest.fixture(scope="module", params=sorted(BACKENDS))
def db(request) -> dict:
    """Connection config of a live database loaded with the lineage fixture."""
    backend = BACKENDS[request.param]
    dsn = os.environ.get(backend.env)
    if not dsn:
        pytest.skip(f"{backend.env} is not set")
    config = _config(backend, dsn)
    sql = (FIXTURES / backend.fixture).read_text()
    (_load_postgresql if backend.name == "postgresql" else _load_mysql)(config, sql)
    return config


def extract(config: dict, objects: list[str] | None = None) -> str:
    from db_connectors import DatabaseConnectorFactory

    with DatabaseConnectorFactory.create_connector(config["type"], config) as connector:
        return connector.extract_ddl(objects)
