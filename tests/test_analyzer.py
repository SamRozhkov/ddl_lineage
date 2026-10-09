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
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255)
        );

        CREATE TABLE user_stats AS
        SELECT id, email AS user_email, count(*) AS total
        FROM users;
        """
        _, r = make(ddl)
        table = next(o for o in r["objects"] if o["name"] == "user_stats")
        assert [c["name"] for c in table["columns"]] == ["id", "user_email", "total"]
        assert [c["type"] for c in table["columns"]] == ["SERIAL", "VARCHAR(255)", ""]

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
        assert [c["type"] for c in view["columns"]] == ["SERIAL", "VARCHAR(255)"]

    def test_view_columns_from_expression_aliases(self):
        ddl = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email TEXT
        );

        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER
        );

        CREATE VIEW user_summary AS
        SELECT u.id AS user_id, COUNT(o.id) AS order_count
        FROM users u
        JOIN orders o ON o.user_id = u.id;
        """
        _, r = make(ddl)
        view = next(o for o in r["objects"] if o["name"] == "user_summary")
        assert [c["name"] for c in view["columns"]] == ["user_id", "order_count"]
        assert [c["type"] for c in view["columns"]] == ["SERIAL", ""]

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


# DDL as PostgreSQL itself dumps it (pg_get_constraintdef / format_type)
PG_CATALOG_DDL = """
CREATE TABLE s.customers (
    id integer NOT NULL DEFAULT nextval('s.customers_id_seq'::regclass),
    email character varying(255) NOT NULL,
    CONSTRAINT customers_email_key UNIQUE (email),
    CONSTRAINT customers_pkey PRIMARY KEY (id)
);
CREATE TABLE s.vip_customers (
    discount numeric(5,2) DEFAULT 0
) INHERITS (s.customers);
CREATE TABLE s.order_items (
    order_id integer NOT NULL,
    line_no integer NOT NULL,
    price numeric(10,2) NOT NULL,
    status character varying(20) NOT NULL DEFAULT 'new'::character varying,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT order_items_pkey PRIMARY KEY (order_id, line_no)
);
CREATE TABLE s.item_returns (
    id integer NOT NULL,
    order_id integer NOT NULL,
    line_no integer NOT NULL,
    customer_id integer,
    CONSTRAINT item_returns_fkey FOREIGN KEY (order_id, line_no) REFERENCES s.order_items(order_id, line_no),
    CONSTRAINT item_returns_customer_fkey FOREIGN KEY (customer_id) REFERENCES s.customers(id)
);
"""


def column(result, table, name):
    obj = next(o for o in result["objects"] if o["name"] == table)
    return next(c for c in obj["columns"] if c["name"] == name)


class TestCatalogStyleDDL:
    def test_multi_word_and_precision_types(self):
        _, r = make(PG_CATALOG_DDL)
        assert column(r, "customers", "email")["type"] == "CHARACTER VARYING(255)"
        assert column(r, "order_items", "price")["type"] == "NUMERIC(10,2)"
        assert column(r, "order_items", "created_at")["type"] == "TIMESTAMP WITHOUT TIME ZONE"
        assert column(r, "vip_customers", "discount")["type"] == "NUMERIC(5,2)"

    def test_defaults_keep_literal_without_cast(self):
        _, r = make(PG_CATALOG_DDL)
        assert column(r, "order_items", "status")["default"] == "new"
        assert column(r, "order_items", "created_at")["default"] == "now()"
        assert column(r, "order_items", "status")["nullable"] is False

    def test_table_level_primary_key_and_unique(self):
        _, r = make(PG_CATALOG_DDL)
        assert column(r, "customers", "id")["pk"] is True
        assert column(r, "customers", "email")["unique"] is True
        assert column(r, "order_items", "order_id")["pk"] is True
        assert column(r, "order_items", "line_no")["pk"] is True
        assert column(r, "order_items", "price")["pk"] is False

    def test_table_level_foreign_keys(self):
        _, r = make(PG_CATALOG_DDL)
        assert column(r, "item_returns", "order_id")["fk_to"] == "order_items.order_id"
        assert column(r, "item_returns", "line_no")["fk_to"] == "order_items.line_no"
        assert column(r, "item_returns", "customer_id")["fk_to"] == "customers.id"
        fks = [e for e in r["edges"] if e["source"] == "item_returns" and e["type"] == "FK"]
        assert sorted((e["target"], e["details"]) for e in fks) == [
            ("customers", "customer_id -> customers.id"),
            ("order_items", "order_id -> order_items.order_id, line_no -> order_items.line_no"),
        ]

    def test_inherits_after_column_list(self):
        _, r = make(PG_CATALOG_DDL)
        assert edge_exists(r, "vip_customers", "customers", "INHERITS")

    def test_inherits_multiple_parents(self):
        _, r = make("CREATE TABLE c (x INT) INHERITS (a, s.b);")
        assert edge_exists(r, "c", "a", "INHERITS")
        assert edge_exists(r, "c", "b", "INHERITS")

    def test_inline_reference_with_schema(self):
        _, r = make("CREATE TABLE a (id INT PRIMARY KEY); CREATE TABLE b (a_id INT REFERENCES s.a(id));")
        assert column(r, "b", "a_id")["fk_to"] == "a.id"
        assert edge_exists(r, "b", "a", "FK")
        assert not any(o["name"] == "s" for o in r["objects"])

    def test_alter_table_foreign_key_sets_column_and_details(self):
        ddl = """
        CREATE TABLE a (id INT PRIMARY KEY);
        CREATE TABLE b (id INT, a_id INT);
        ALTER TABLE ONLY s.b ADD CONSTRAINT b_fk FOREIGN KEY (a_id) REFERENCES s.a(id);
        """
        _, r = make(ddl)
        assert column(r, "b", "a_id")["fk_to"] == "a.id"
        fks = [e for e in r["edges"] if e["source"] == "b" and e["type"] == "FK"]
        assert [(e["target"], e["details"]) for e in fks] == [("a", "a_id -> a.id")]


MYSQL_ROUTINES_DDL = """
CREATE TABLE cart (id INT PRIMARY KEY);
CREATE TABLE cart_items (cart_id INT, qty INT);
CREATE TABLE orders (id INT, total INT);

CREATE PROCEDURE checkout(IN p_cart_id INT)
BEGIN
  DECLARE v_total INT;
  SELECT SUM(qty) INTO v_total FROM cart_items WHERE cart_id = p_cart_id;
  IF v_total > 0 THEN
    INSERT INTO orders(total) VALUES (CASE WHEN v_total > 10 THEN v_total ELSE 0 END);
  END IF;
  DELETE FROM cart_items WHERE cart_id = p_cart_id;
  DELETE FROM cart WHERE id = p_cart_id;
END;

CREATE FUNCTION cart_size(p INT) RETURNS INT
READS SQL DATA
BEGIN
  RETURN (SELECT COUNT(*) FROM cart_items WHERE cart_id = p);
END;

BEGIN;
CREATE VIEW big_orders AS SELECT id FROM orders WHERE total > 100;
"""


class TestMySQLRoutines:
    def test_procedure_body_is_not_split_on_semicolons(self):
        _, r = make(MYSQL_ROUTINES_DDL)
        assert edge_exists(r, "checkout", "cart_items", "WRITE")
        assert edge_exists(r, "checkout", "cart", "WRITE")
        assert edge_exists(r, "checkout", "orders", "WRITE")
        assert edge_exists(r, "checkout", "cart_items", "READ")

    def test_function_and_following_statements(self):
        _, r = make(MYSQL_ROUTINES_DDL)
        assert edge_exists(r, "cart_size", "cart_items", "READ")
        assert edge_exists(r, "big_orders", "orders", "READ")

    def test_definer_and_algorithm_options(self):
        ddl = """
        CREATE TABLE `t` (`id` int NOT NULL, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`%` SQL SECURITY DEFINER VIEW `v` AS
            select `t`.`id` AS `id` from `t`;
        CREATE DEFINER=`app`@`10.0.%` PROCEDURE `p`(IN x INT)
        BEGIN
          DELETE FROM `t` WHERE id = x;
        END;
        CREATE DEFINER=CURRENT_USER FUNCTION `f`(x INT) RETURNS int
            READS SQL DATA
        BEGIN
          RETURN (SELECT COUNT(*) FROM `t`);
        END;
        """
        _, r = make(ddl)
        assert {(o["name"], o["type"]) for o in r["objects"]} == {
            ("t", "TABLE"), ("v", "VIEW"), ("p", "PROCEDURE"), ("f", "FUNCTION"),
        }
        assert column(r, "t", "id")["pk"] is True
        assert edge_exists(r, "v", "t", "READ")
        assert edge_exists(r, "p", "t", "WRITE")
        assert edge_exists(r, "f", "t", "READ")

    def test_update_with_alias_and_join(self):
        ddl = """
        CREATE PROCEDURE p()
        BEGIN
          UPDATE products AS pr SET pr.stock = 0;
          UPDATE stock_levels s JOIN order_items oi ON oi.product_id = s.id SET s.qty = s.qty - oi.quantity;
          SELECT id FROM orders FOR UPDATE;
          INSERT INTO audit(id) VALUES (1) ON DUPLICATE KEY UPDATE id = id;
        END;
        """
        _, r = make(ddl)
        assert edge_exists(r, "p", "products", "WRITE")
        assert edge_exists(r, "p", "stock_levels", "WRITE")
        assert flow_exists(r, "order_items", "stock_levels", "WRITE")
        writes = {e["target"] for e in r["edges"] if e["type"] == "WRITE"}
        assert writes == {"products", "stock_levels", "audit"}

    def test_shipped_mysql_example(self):
        from pathlib import Path
        ddl = (Path(__file__).resolve().parents[1] / "examples" / "mysql_style.sql").read_text()
        _, r = make(ddl)
        assert edge_exists(r, "checkout", "cart_items", "WRITE")
        assert edge_exists(r, "checkout", "cart", "WRITE")


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

class TestReadReferenceForms:
    def reads(self, select):
        _, r = make(f"CREATE VIEW v AS {select};")
        return sorted(e["target"] for e in r["edges"] if e["type"] == "READ")

    def test_comma_separated_from_list(self):
        assert self.reads("SELECT * FROM a, s.b bb, c AS cc WHERE a.id = bb.id") == ["a", "b", "c"]

    def test_parenthesised_join_tree(self):
        # MySQL rewrites stored views like this
        sql = (
            "select `o`.`id` AS `id` from ((`orders` `o` join `customers` `c` on((`c`.`id` = `o`.`customer_id`))) "
            "join `lineage_it`.`payments` `p` on((`p`.`order_id` = `o`.`id`)))"
        )
        assert self.reads(sql) == ["customers", "orders", "payments"]

    def test_join_with_nested_join(self):
        assert self.reads("SELECT x FROM t JOIN (u JOIN w ON u.id = w.id) ON true") == ["t", "u", "w"]

    def test_subquery_is_not_a_table(self):
        assert self.reads("SELECT x FROM (SELECT id FROM t) sub, (VALUES (1)) vals(x)") == ["t"]

    def test_from_inside_functions_is_not_a_table(self):
        sql = (
            "SELECT EXTRACT(YEAR FROM created_at) y, SUBSTRING(name FROM 2 FOR 3) s, "
            "TRIM(BOTH ' ' FROM name) t2 FROM orders"
        )
        assert self.reads(sql) == ["orders"]


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
# Tables created inside functions + statement-level flows
# ---------------------------------------------------------------------------

FN_TABLES_DDL = """
CREATE TABLE orders (id SERIAL PRIMARY KEY, amount DECIMAL(10,2));
CREATE TABLE reports (total DECIMAL(12,2));

CREATE FUNCTION build_stage() RETURNS VOID AS $$
BEGIN
    CREATE TEMP TABLE stage_orders AS
        SELECT id, amount FROM orders;
    INSERT INTO reports(total) SELECT SUM(amount) FROM stage_orders;
    UPDATE orders SET amount = 0;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION use_stage() RETURNS INT AS $$
BEGIN
    RETURN (SELECT COUNT(*) FROM stage_orders);
END;
$$ LANGUAGE plpgsql;
"""


def flow_exists(result, src, tgt, ftype=None):
    return any(
        f["source"] == src and f["target"] == tgt and (ftype is None or f["type"] == ftype)
        for f in result["flows"]
    )


class TestFunctionTables:
    def test_table_created_in_function_has_parent(self):
        _, r = make(FN_TABLES_DDL)
        obj = next(o for o in r["objects"] if o["name"] == "stage_orders")
        assert obj["type"] == "TABLE"
        assert obj["temporary"] is True
        assert obj["parent"] == "build_stage"
        assert [c["name"] for c in obj["columns"]] == ["id", "amount"]

    def test_top_level_tables_have_no_parent(self):
        _, r = make(FN_TABLES_DDL)
        orders = next(o for o in r["objects"] if o["name"] == "orders")
        assert orders["parent"] == ""

    def test_top_level_definition_wins_over_function(self):
        ddl = """
        CREATE FUNCTION f() RETURNS VOID AS $$
        BEGIN
            CREATE TABLE IF NOT EXISTS t (id INT);
        END;
        $$ LANGUAGE plpgsql;
        CREATE TABLE t (id INT, name TEXT);
        """
        _, r = make(ddl)
        t = next(o for o in r["objects"] if o["name"] == "t")
        assert t["parent"] == ""
        assert len(t["columns"]) == 2

    def test_create_in_function_is_write_edge(self):
        _, r = make(FN_TABLES_DDL)
        assert edge_exists(r, "build_stage", "stage_orders", "WRITE")

    def test_flow_from_source_into_created_table(self):
        _, r = make(FN_TABLES_DDL)
        assert flow_exists(r, "orders", "stage_orders", "WRITE")

    def test_flow_between_tables_inside_function(self):
        _, r = make(FN_TABLES_DDL)
        assert flow_exists(r, "stage_orders", "reports", "WRITE")
        assert not flow_exists(r, "build_stage", "reports")

    def test_write_without_source_flows_from_function(self):
        _, r = make(FN_TABLES_DDL)
        assert flow_exists(r, "build_stage", "orders", "WRITE")

    def test_read_without_target_flows_into_function(self):
        _, r = make(FN_TABLES_DDL)
        assert flow_exists(r, "stage_orders", "use_stage", "READ")

    def test_update_from_flows_source_to_target(self):
        ddl = """
        CREATE FUNCTION f() RETURNS VOID AS $$
        BEGIN
            UPDATE products SET stock = stock - oi.quantity
            FROM order_items oi WHERE oi.product_id = products.id;
            DELETE FROM carts;
        END;
        $$ LANGUAGE plpgsql;
        """
        _, r = make(ddl)
        assert flow_exists(r, "order_items", "products", "WRITE")
        assert flow_exists(r, "f", "carts", "WRITE")
        assert not flow_exists(r, "carts", "carts")


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

    def test_to_text_shows_function_tables_and_flows(self):
        a, r = make(FN_TABLES_DDL)
        out = a.to_text(r)
        assert "stage_orders  [TEMP, created in build_stage]" in out
        assert "Data flows" in out
        assert "orders" in out.split("Data flows")[1].split("stage_orders")[0]

    def test_to_text_without_flows_has_no_flow_section(self):
        a, r = make("CREATE TABLE t (id INT); CREATE VIEW v AS SELECT id FROM t;")
        assert "Data flows" not in a.to_text(r)

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

    def test_to_dot_groups_function_tables_and_draws_flows(self):
        a, r = make(FN_TABLES_DDL)
        out = a.to_dot(r)
        cluster = out.split('subgraph "cluster_build_stage"')[1].split("}")[0]
        assert '"build_stage" [label=' in cluster
        assert '"stage_orders" [label=' in cluster
        assert '"orders" -> "stage_orders" [' in out
        assert 'label="flow CREATE"' in out

    def test_to_dot_without_flows_has_no_clusters(self):
        a, r = make("CREATE TABLE t (id INT); CREATE VIEW v AS SELECT id FROM t;")
        assert "subgraph" not in a.to_dot(r)

    def test_to_mermaid_groups_function_tables_and_draws_flows(self):
        a, r = make(FN_TABLES_DDL)
        out = a.to_mermaid(r)
        group = out.split('subgraph build_stage_group["ƒ build_stage"]')[1].split("  end")[0]
        assert "build_stage[" in group
        assert "stage_orders[" in group
        assert '  orders ==>|"CREATE"| stage_orders' in out
        assert '  stage_orders ==>|"INSERT"| reports' in out


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
