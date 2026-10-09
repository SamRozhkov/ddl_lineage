"""
Integration tests: live database -> connector DDL extract -> lineage.

Both fixtures (fixtures/postgres_lineage.sql, fixtures/mysql_lineage.sql)
describe the same shop schema. The expected dependencies below are written by
hand from them, so the tests catch analyzer mistakes too, not only differences
between the extract and the source SQL. See conftest.py for how to run them.
"""

from __future__ import annotations

import pytest

from ddl_lineage import DDLLineageAnalyzer

from .conftest import extract

COMMON_OBJECTS = {
    ("customers", "TABLE", ""),
    ("products", "TABLE", ""),
    ("orders", "TABLE", ""),
    ("order_items", "TABLE", ""),
    ("item_returns", "TABLE", ""),
    ("payments", "TABLE", ""),
    ("daily_report", "TABLE", ""),
    ("orders_archive", "TABLE", ""),
    ("active_orders", "VIEW", ""),
    ("order_totals", "VIEW", ""),
    ("big_spenders", "VIEW", ""),
    ("customer_count", "FUNCTION", ""),
    ("orders_of", "FUNCTION", ""),
    ("archive_orders", "PROCEDURE", ""),
    ("stage_sales", "TABLE", "build_daily_report"),   # temp table created in the body
}

EXPECTED_OBJECTS = {
    "postgresql": COMMON_OBJECTS | {
        ("vip_customers", "TABLE", ""),
        ("product_sales", "MATERIALIZED_VIEW", ""),
        ("process_order", "FUNCTION", ""),
        ("build_daily_report", "FUNCTION", ""),
    },
    "mysql": COMMON_OBJECTS | {
        ("process_order", "PROCEDURE", ""),
        ("build_daily_report", "PROCEDURE", ""),
    },
}

# (source, type, target): source depends on target
COMMON_EDGES = {
    ("orders", "FK", "customers"),
    ("order_items", "FK", "orders"),
    ("order_items", "FK", "products"),
    ("item_returns", "FK", "order_items"),
    ("payments", "FK", "orders"),
    ("active_orders", "READ", "orders"),
    ("active_orders", "READ", "customers"),
    ("order_totals", "READ", "order_items"),
    ("order_totals", "READ", "products"),
    ("big_spenders", "READ", "order_totals"),
    ("big_spenders", "READ", "orders"),
    ("big_spenders", "READ", "customers"),
    ("process_order", "READ", "order_items"),
    ("process_order", "READ", "products"),
    ("process_order", "WRITE", "payments"),
    ("process_order", "WRITE", "products"),
    ("process_order", "WRITE", "orders"),
    ("build_daily_report", "READ", "orders"),
    ("build_daily_report", "READ", "order_items"),
    ("build_daily_report", "READ", "products"),
    ("build_daily_report", "READ", "stage_sales"),
    ("build_daily_report", "WRITE", "stage_sales"),
    ("build_daily_report", "WRITE", "daily_report"),
    ("customer_count", "READ", "customers"),
    ("orders_of", "READ", "orders"),
    ("archive_orders", "READ", "orders"),
    ("archive_orders", "WRITE", "orders_archive"),
    ("archive_orders", "WRITE", "orders"),
}

EXPECTED_EDGES = {
    "postgresql": COMMON_EDGES | {
        ("vip_customers", "INHERITS", "customers"),
        ("product_sales", "READ", "products"),
        ("product_sales", "READ", "order_items"),
    },
    "mysql": COMMON_EDGES,
}

# (source, target, details, via): data moves source -> target
EXPECTED_FLOWS = {
    ("order_items", "payments", "INSERT", "process_order"),
    ("products", "payments", "INSERT", "process_order"),
    ("order_items", "products", "UPDATE", "process_order"),
    ("process_order", "orders", "UPDATE", "process_order"),
    ("orders", "stage_sales", "CREATE", "build_daily_report"),
    ("order_items", "stage_sales", "CREATE", "build_daily_report"),
    ("products", "stage_sales", "CREATE", "build_daily_report"),
    ("stage_sales", "daily_report", "INSERT", "build_daily_report"),
    ("customers", "customer_count", "", "customer_count"),
    ("orders", "orders_of", "", "orders_of"),
    ("orders", "orders_archive", "INSERT", "archive_orders"),
    ("archive_orders", "orders", "DELETE", "archive_orders"),
}


@pytest.fixture(scope="module")
def result(db) -> dict:
    return DDLLineageAnalyzer().analyze(extract(db))


def _object(result: dict, name: str) -> dict:
    return next(o for o in result["objects"] if o["name"] == name)


def _column(result: dict, table: str, name: str) -> dict:
    return next(c for c in _object(result, table)["columns"] if c["name"] == name)


def test_objects(db, result):
    assert {(o["name"], o["type"], o["parent"]) for o in result["objects"]} == EXPECTED_OBJECTS[db["type"]]


def test_other_schemas_are_not_extracted(db):
    ddl = extract(db)
    assert "lineage_it_noise" not in ddl
    assert "leaky" not in ddl


def test_edges(db, result):
    assert {(e["source"], e["type"], e["target"]) for e in result["edges"]} == EXPECTED_EDGES[db["type"]]


def test_flows(result):
    assert {(f["source"], f["target"], f["details"], f["via"]) for f in result["flows"]} == EXPECTED_FLOWS


def test_topological_order(result):
    assert result["cycles"] == []
    order = result["topo_order"]
    assert order.index("customers") < order.index("orders") < order.index("order_items")
    assert order.index("order_totals") < order.index("big_spenders")


def test_columns_from_catalog(result):
    assert _column(result, "customers", "id")["pk"] is True
    assert _column(result, "customers", "email")["type"] in ("CHARACTER VARYING(255)", "VARCHAR(255)")
    assert _column(result, "customers", "email")["unique"] is True
    assert _column(result, "order_items", "order_id")["pk"] is True
    assert _column(result, "order_items", "line_no")["pk"] is True
    assert _column(result, "order_items", "product_id")["fk_to"] == "products.id"
    assert _column(result, "item_returns", "line_no")["fk_to"] == "order_items.line_no"
    assert _column(result, "daily_report", "total")["type"] in ("NUMERIC(14,2)", "DECIMAL(14,2)")
    assert _column(result, "orders", "status")["default"] == "new"


def test_inherited_columns_stay_on_parent(db, result):
    if db["type"] != "postgresql":
        pytest.skip("table inheritance is PostgreSQL-only")
    assert [c["name"] for c in _object(result, "vip_customers")["columns"]] == ["discount"]


def test_composite_foreign_key_is_one_edge(result):
    fks = [e for e in result["edges"] if e["source"] == "item_returns" and e["type"] == "FK"]
    assert [e["details"] for e in fks] == [
        "order_id -> order_items.order_id, line_no -> order_items.line_no"
    ]


def test_column_lineage_through_routine(result):
    col_lineage = {(c["src_table"], c["src_col"], c["tgt_table"], c["tgt_col"]) for c in result["col_lineage"]}
    assert ("orders", "id", "orders_archive", "id") in col_lineage
    assert ("orders", "created_at", "orders_archive", "created_at") in col_lineage


def test_object_filter(db):
    ddl = extract(db, ["orders", "active_orders", "process_order"])
    names = {o["name"] for o in DDLLineageAnalyzer().analyze(ddl)["objects"]}
    # The selected objects plus the tables they reference (auto-registered)
    assert {"orders", "active_orders", "process_order"} <= names
    assert not names & {"big_spenders", "archive_orders", "orders_archive"}


def test_web_api_connect_then_analyze(db, monkeypatch):
    import app as web_app

    saved: dict = {}

    class MemoryStore:
        def save_state(self, name, state, action):
            saved[action] = state

    monkeypatch.setattr(web_app, "project_store", MemoryStore())
    client = web_app.app.test_client()

    resp = client.post("/api/connect", json={**db, "project_name": "it"})
    assert resp.status_code == 200, resp.json
    assert "password" not in saved["db_connect"]["connection"]

    resp = client.post("/api/analyze", json={"ddl": resp.json["ddl"], "project_name": "it"})
    assert resp.status_code == 200, resp.json
    edges = {(e["source"], e["type"], e["target"]) for e in resp.json["data"]["edges"]}
    assert edges == EXPECTED_EDGES[db["type"]]
    assert len(saved["analysis"]["analysis"]["flows"]) == len(EXPECTED_FLOWS)
