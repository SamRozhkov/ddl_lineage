"""
Web backend API (Flask test client, no database).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("flask")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web" / "backend"))

from ddl_lineage import DDLLineageAnalyzer  # noqa: E402

DDL = """
CREATE TABLE orders (id SERIAL PRIMARY KEY, amount DECIMAL(10,2));
CREATE TABLE reports (total DECIMAL(12,2));
CREATE FUNCTION build_stage() RETURNS VOID AS $$
BEGIN
    CREATE TEMP TABLE stage_orders AS SELECT id, amount FROM orders;
    INSERT INTO reports(total) SELECT SUM(amount) FROM stage_orders;
END;
$$ LANGUAGE plpgsql;
"""


@pytest.fixture
def api(monkeypatch):
    import app as web_app

    saved: dict = {}

    class MemoryStore:
        def save_state(self, name, state, action):
            saved[action] = state

    monkeypatch.setattr(web_app, "project_store", MemoryStore())
    return web_app.app.test_client(), saved


def test_analyze_returns_analyzer_mermaid(api):
    client, _ = api
    resp = client.post("/api/analyze", json={"ddl": DDL})
    assert resp.status_code == 200, resp.json
    expected = DDLLineageAnalyzer().analyze(DDL)
    assert resp.json["mermaid"] == DDLLineageAnalyzer().to_mermaid(expected)
    assert 'subgraph build_stage_group["ƒ build_stage"]' in resp.json["mermaid"]
    assert 'stage_orders ==>|"INSERT"| reports' in resp.json["mermaid"]


def test_analyze_persists_full_analysis_and_mermaid(api):
    client, saved = api
    resp = client.post("/api/analyze", json={"ddl": DDL, "project_name": "p"})
    assert resp.status_code == 200, resp.json
    state = saved["analysis"]
    assert state["analysis"]["flows"] == resp.json["data"]["flows"]
    assert state["analysis"]["col_lineage"] == resp.json["data"]["col_lineage"]
    assert state["mermaid"] == resp.json["mermaid"]


def test_analyze_rejects_empty_ddl(api):
    client, _ = api
    resp = client.post("/api/analyze", json={"ddl": "   "})
    assert resp.status_code == 400
