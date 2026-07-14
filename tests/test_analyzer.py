"""
tests/test_analyzer.py
======================
Unit tests for DDLLineageAnalyzer.
"""

import pytest
from ddl_lineage import DDLLineageAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASIC_DDL = """
CREATE TABLE users (
    id    SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE orders (
    id      SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    status  VARCHAR(50) DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL,
    quantity   INTEGER NOT NULL
);

CREATE TABLE payments (
    id       SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    amount   DECIMAL(10,2)
);

CREATE VIEW active_orders AS
    SELECT o.id, u.email
    FROM   orders o
    JOIN   users  u ON o.user_id = u.id
    WHERE  o.status = 'active';

CREATE OR REPLACE FUNCTION process_order(p_id INT) RETURNS VOID AS $$
BEGIN
    INSERT INTO payments(order_id, amount, paid_at)
    SELECT order_id, SUM(quantity * 10), NOW()
    FROM   order_items
    WHERE  order_id = p_id
    GROUP  BY order_id;

    UPDATE orders SET status = 'paid' WHERE id = p_id;
END;
$$ LANGUAGE plpgsql;
"""

CYCLE_DDL = """
CREATE VIEW v_a AS SELECT * FROM v_b;
CREATE VIEW v_b AS SELECT * FROM v_c;
CREATE VIEW v_c AS SELECT * FROM v_a;
"""

MYSQL_DDL = """
CREATE TABLE `categories` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `parent_id` INT DEFAULT NULL,
  PRIMARY KEY (`id`),
  FOREIGN KEY (`parent_id`) REFERENCES `categories` (`id`)
);

CREATE TABLE `products` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  `category_id` INT,
  PRIMARY KEY (`id`),
  FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`)
);
"""

TEMP_DDL = """
CREATE TEMP TABLE session_orders (
    id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id)
);

CREATE TEMPORARY TABLE IF NOT EXISTS tmp_users (
    id INTEGER PRIMARY KEY
);

CREATE GLOBAL TEMPORARY TABLE temp_report (
    id INTEGER PRIMARY KEY
);
"""

ALTER_DDL = """
CREATE TABLE a (id SERIAL PRIMARY KEY);
CREATE TABLE b (id SERIAL PRIMARY KEY);
ALTER TABLE b ADD COLUMN a_id INTEGER;
ALTER TABLE b ADD FOREIGN KEY (a_id) REFERENCES a(id);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make(ddl: str) -> tuple[DDLLineageAnalyzer, dict]:
    a = DDLLineageAnalyzer()
    return a, a.analyze(ddl)


def edge_exists(result, src, tgt, etype=None):
    for e in result["edges"]:
        if e["source"] == src and e["target"] == tgt:
            if etype is None or e["type"] == etype:
                return True
    return False


def obj_exists(result, name, otype=None):
    for o in result["objects"]:
        if o["name"] == name:
            if otype is None or o["type"] == otype:
                return True
    return False


# ---------------------------------------------------------------------------
# Object parsing
# ---------------------------------------------------------------------------

class TestObjectParsing:
    def test_tables_detected(self):
        _, r = make(BASIC_DDL)
        for name in ("users", "orders", "order_items", "payments"):
            assert obj_exists(r, name, "TABLE"), f"Missing table: {name}"

    def test_view_detected(self):
        _, r = make(BASIC_DDL)
        assert obj_exists(r, "active_orders", "VIEW")

    def test_function_detected(self):
        _, r = make(BASIC_DDL)
        assert obj_exists(r, "process_order", "FUNCTION")

    def test_mysql_backtick_tables(self):
        _, r = make(MYSQL_DDL)
        assert obj_exists(r, "categories", "TABLE")
        assert obj_exists(r, "products", "TABLE")

    def test_temp_tables_marked(self):
        _, r = make(TEMP_DDL)
        temp_names = {"session_orders", "tmp_users", "temp_report"}
        for name in temp_names:
            obj = next(o for o in r["objects"] if o["name"] == name)
            assert obj["type"] == "TABLE"
            assert obj["temporary"] is True

    def test_create_temp_table_short_form_marked(self):
        _, r = make("CREATE TEMP TABLE t (id INTEGER);")
        obj = next(o for o in r["objects"] if o["name"] == "t")
        assert obj["type"] == "TABLE"
        assert obj["temporary"] is True

    def test_create_temp_table_if_not_exists_as_select_marked(self):
        ddl = """
        CREATE TEMP TABLE IF NOT EXISTS sng_hr.fer_pre_appointments AS
            SELECT 1 AS id;
        """
        _, r = make(ddl)
        obj = next(o for o in r["objects"] if o["name"] == "fer_pre_appointments")
        assert obj["schema"] == "sng_hr"
        assert obj["type"] == "TABLE"
        assert obj["temporary"] is True

    def test_implicit_object_auto_registered(self):
        ddl = "CREATE VIEW v AS SELECT * FROM nonexistent_table;"
        _, r = make(ddl)
        assert obj_exists(r, "nonexistent_table")


# ---------------------------------------------------------------------------
# Column parsing
# ---------------------------------------------------------------------------

class TestColumnParsing:
    def test_pk_column(self):
        _, r = make(BASIC_DDL)
        users = next(o for o in r["objects"] if o["name"] == "users")
        id_col = next((c for c in users["columns"] if c["name"] == "id"), None)
        assert id_col is not None
        assert id_col["pk"] is True
        assert id_col["nullable"] is False

    def test_unique_column(self):
        _, r = make(BASIC_DDL)
        users = next(o for o in r["objects"] if o["name"] == "users")
        email_col = next((c for c in users["columns"] if c["name"] == "email"), None)
        assert email_col is not None
        assert email_col["unique"] is True

    def test_default_value(self):
        _, r = make(BASIC_DDL)
        orders = next(o for o in r["objects"] if o["name"] == "orders")
        status_col = next((c for c in orders["columns"] if c["name"] == "status"), None)
        assert status_col is not None
        assert "pending" in status_col["default"]

    def test_inline_fk_column(self):
        _, r = make(BASIC_DDL)
        payments = next(o for o in r["objects"] if o["name"] == "payments")
        oi_col = next((c for c in payments["columns"] if c["name"] == "order_id"), None)
        assert oi_col is not None
        assert "orders" in oi_col["fk_to"]

    def test_create_table_as_select_columns(self):
        ddl = """
        CREATE TABLE user_stats AS
        SELECT id, email AS user_email, count(*) AS total
        FROM users;
        """
        _, r = make(ddl)
        table = next(o for o in r["objects"] if o["name"] == "user_stats")
        assert [c["name"] for c in table["columns"]] == ["id", "user_email", "total"]

    def test_create_table_as_select_ignores_expression_parentheses(self):
        ddl = """
        CREATE TABLE normalized_users AS
        SELECT CAST(id AS INTEGER) AS user_id, COALESCE(email, 'unknown') AS email
        FROM users;
        """
        _, r = make(ddl)
        table = next(o for o in r["objects"] if o["name"] == "normalized_users")
        assert [c["name"] for c in table["columns"]] == ["user_id", "email"]

    def test_view_columns_from_select_list(self):
        _, r = make(BASIC_DDL)
        view = next(o for o in r["objects"] if o["name"] == "active_orders")
        assert [c["name"] for c in view["columns"]] == ["id", "email"]

    def test_view_columns_from_expression_aliases(self):
        ddl = """
        CREATE VIEW user_summary AS
        SELECT u.id AS user_id, COUNT(o.id) AS order_count
        FROM users u
        JOIN orders o ON o.user_id = u.id;
        """
        _, r = make(ddl)
        view = next(o for o in r["objects"] if o["name"] == "user_summary")
        assert [c["name"] for c in view["columns"]] == ["user_id", "order_count"]

    def test_function_returns_table_columns(self):
        ddl = """
        CREATE FUNCTION get_active_users()
        RETURNS TABLE (user_id INTEGER, email TEXT)
        AS $$
        BEGIN
            RETURN QUERY SELECT id, email FROM users;
        END;
        $$ LANGUAGE plpgsql;
        """
        _, r = make(ddl)
        fn = next(o for o in r["objects"] if o["name"] == "get_active_users")
        assert [c["name"] for c in fn["columns"]] == ["user_id", "email"]

    def test_function_returns_setof_known_table_columns(self):
        ddl = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email TEXT
        );

        CREATE FUNCTION list_users()
        RETURNS SETOF users
        AS $$
        BEGIN
            RETURN QUERY SELECT * FROM users;
        END;
        $$ LANGUAGE plpgsql;
        """
        _, r = make(ddl)
        fn = next(o for o in r["objects"] if o["name"] == "list_users")
        assert [c["name"] for c in fn["columns"]] == ["id", "email"]


# ---------------------------------------------------------------------------
# FK edges
# ---------------------------------------------------------------------------

class TestForeignKeys:
    def test_explicit_fk(self):
        _, r = make(BASIC_DDL)
        assert edge_exists(r, "orders", "users", "FK")

    def test_inline_fk(self):
        _, r = make(BASIC_DDL)
        assert edge_exists(r, "order_items", "orders", "FK")

    def test_self_referencing_fk(self):
        _, r = make(MYSQL_DDL)
        # categories.parent_id -> categories — self-ref should NOT create an edge
        fk_edges = [e for e in r["edges"]
                    if e["source"] == "categories" and e["target"] == "categories"]
        assert len(fk_edges) == 0

    def test_alter_table_fk(self):
        _, r = make(ALTER_DDL)
        assert edge_exists(r, "b", "a", "FK")


# ---------------------------------------------------------------------------
# READ edges
# ---------------------------------------------------------------------------

class TestReadEdges:
    def test_view_reads_tables(self):
        _, r = make(BASIC_DDL)
        assert edge_exists(r, "active_orders", "orders", "READ")
        assert edge_exists(r, "active_orders", "users", "READ")

    def test_function_reads_table(self):
        _, r = make(BASIC_DDL)
        assert edge_exists(r, "process_order", "order_items", "READ")

    def test_cte_not_treated_as_table(self):
        ddl = """
        CREATE VIEW v AS
        WITH cte AS (SELECT id FROM users)
        SELECT * FROM cte;
        """
        _, r = make(ddl)
        assert not edge_exists(r, "v", "cte")
        assert edge_exists(r, "v", "users", "READ")


# ---------------------------------------------------------------------------
# WRITE edges
# ---------------------------------------------------------------------------

class TestWriteEdges:
    def test_insert_write(self):
        _, r = make(BASIC_DDL)
        assert edge_exists(r, "process_order", "payments", "WRITE")

    def test_update_write(self):
        _, r = make(BASIC_DDL)
        assert edge_exists(r, "process_order", "orders", "WRITE")

    def test_write_detail_label(self):
        _, r = make(BASIC_DDL)
        pay_edge = next(
            e for e in r["edges"]
            if e["source"] == "process_order" and e["target"] == "payments" and e["type"] == "WRITE"
        )
        assert pay_edge["details"] == "INSERT"


# ---------------------------------------------------------------------------
# Column lineage
# ---------------------------------------------------------------------------

class TestColumnLineage:
    def test_col_lineage_extracted(self):
        _, r = make(BASIC_DDL)
        assert len(r["col_lineage"]) > 0

    def test_col_lineage_fields(self):
        _, r = make(BASIC_DDL)
        for cl in r["col_lineage"]:
            assert "src_table" in cl and "src_col" in cl
            assert "tgt_table" in cl and "tgt_col" in cl
            assert "via" in cl


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    def test_no_cycles_basic(self):
        _, r = make(BASIC_DDL)
        assert r["stats"]["has_cycles"] is False

    def test_cycles_detected(self):
        _, r = make(CYCLE_DDL)
        assert r["stats"]["has_cycles"] is True
        assert len(r["cycles"]) > 0

    def test_cycle_contains_all_nodes(self):
        _, r = make(CYCLE_DDL)
        all_nodes = {n for cyc in r["cycles"] for n in cyc}
        for name in ("v_a", "v_b", "v_c"):
            assert name in all_nodes


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------

class TestImpactAnalysis:
    def test_upstream(self):
        a, _ = make(BASIC_DDL)
        a.analyze(BASIC_DDL)
        imp = a.impact("orders")
        assert "users" in imp.upstream

    def test_downstream(self):
        a, _ = make(BASIC_DDL)
        a.analyze(BASIC_DDL)
        imp = a.impact("orders")
        assert "order_items" in imp.downstream or "active_orders" in imp.downstream

    def test_unknown_object(self):
        a, _ = make(BASIC_DDL)
        a.analyze(BASIC_DDL)
        imp = a.impact("nonexistent")
        assert imp.upstream == []
        assert imp.downstream == []


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------

class TestOutputFormats:
    def test_to_text(self):
        a, r = make(BASIC_DDL)
        out = a.to_text(r)
        assert "TABLEs" in out
        assert "Lineage edges" in out
        assert "users" in out

    def test_to_json(self):
        import json
        a, r = make(BASIC_DDL)
        out = a.to_json(r)
        parsed = json.loads(out)
        assert "objects" in parsed
        assert "edges" in parsed

    def test_to_dot(self):
        a, r = make(BASIC_DDL)
        out = a.to_dot(r)
        assert "digraph" in out
        assert "users" in out

    def test_to_mermaid(self):
        a, r = make(BASIC_DDL)
        out = a.to_mermaid(r)
        assert "graph LR" in out
        assert "users" in out


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_fields(self):
        _, r = make(BASIC_DDL)
        s = r["stats"]
        assert "total_objects" in s
        assert "total_edges" in s
        assert "has_cycles" in s

    def test_topo_order(self):
        _, r = make(BASIC_DDL)
        assert "topo_order" in r
        assert len(r["topo_order"]) == len(r["objects"])

    def test_topo_dependencies_before_dependents(self):
        _, r = make(BASIC_DDL)
        order = r["topo_order"]
        assert order.index("users") < order.index("orders")
        assert order.index("orders") < order.index("active_orders")
        assert order.index("order_items") < order.index("process_order")
