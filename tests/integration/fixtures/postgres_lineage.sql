-- Test schema for the PostgreSQL connector integration tests.
-- Idempotent: recreates only the lineage_it / lineage_it_noise schemas.

DROP SCHEMA IF EXISTS lineage_it_noise CASCADE;
DROP SCHEMA IF EXISTS lineage_it CASCADE;
CREATE SCHEMA lineage_it;
SET search_path TO lineage_it;

CREATE TABLE customers (
    id      SERIAL PRIMARY KEY,
    email   VARCHAR(255) NOT NULL UNIQUE,
    country VARCHAR(2)
);

CREATE TABLE vip_customers (
    discount NUMERIC(5,2) DEFAULT 0
) INHERITS (customers);

CREATE TABLE products (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    status      VARCHAR(20) NOT NULL DEFAULT 'new',
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    line_no    INTEGER NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_no)
);

-- Composite foreign key
CREATE TABLE item_returns (
    id       SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    line_no  INTEGER NOT NULL,
    reason   TEXT,
    FOREIGN KEY (order_id, line_no) REFERENCES order_items(order_id, line_no)
);

CREATE TABLE payments (
    id       SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    amount   NUMERIC(12,2) NOT NULL
);

CREATE TABLE daily_report (
    day   DATE PRIMARY KEY,
    total NUMERIC(14,2) NOT NULL
);

CREATE TABLE orders_archive (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status      VARCHAR(20) NOT NULL,
    created_at  TIMESTAMP NOT NULL
);

-- Views (one built on top of another)
CREATE VIEW active_orders AS
    SELECT o.id, o.created_at, c.email
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.status = 'active';

CREATE VIEW order_totals AS
    SELECT oi.order_id, SUM(oi.quantity * p.price) AS total
    FROM order_items oi
    JOIN products p ON p.id = oi.product_id
    GROUP BY oi.order_id;

CREATE VIEW big_spenders AS
    SELECT c.email, SUM(t.total) AS spent
    FROM order_totals t
    JOIN orders o ON o.id = t.order_id
    JOIN customers c ON c.id = o.customer_id
    GROUP BY c.email
    HAVING SUM(t.total) > 1000;

CREATE MATERIALIZED VIEW product_sales AS
    SELECT p.id, p.name, SUM(oi.quantity) AS sold
    FROM products p
    JOIN order_items oi ON oi.product_id = p.id
    GROUP BY p.id, p.name;

-- Functions / procedures
CREATE FUNCTION process_order(p_order_id INTEGER) RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO payments(order_id, amount)
    SELECT oi.order_id, SUM(oi.quantity * p.price)
    FROM order_items oi
    JOIN products p ON p.id = oi.product_id
    WHERE oi.order_id = p_order_id
    GROUP BY oi.order_id;

    UPDATE products SET stock = stock - oi.quantity
    FROM order_items oi
    WHERE oi.product_id = products.id AND oi.order_id = p_order_id;

    UPDATE orders SET status = 'paid' WHERE id = p_order_id;
END;
$$;

CREATE FUNCTION build_daily_report(p_day DATE) RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
    CREATE TEMP TABLE stage_sales AS
        SELECT o.id, oi.quantity * p.price AS amount
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        WHERE o.created_at::date = p_day;

    INSERT INTO daily_report(day, total)
    SELECT p_day, COALESCE(SUM(amount), 0) FROM stage_sales;

    DROP TABLE stage_sales;
END;
$$;

CREATE FUNCTION customer_count() RETURNS BIGINT
LANGUAGE plpgsql AS $$
BEGIN
    RETURN (SELECT COUNT(*) FROM customers);
END;
$$;

CREATE FUNCTION orders_of(p_customer INTEGER) RETURNS BIGINT
LANGUAGE sql AS $$
    SELECT COUNT(*) FROM orders WHERE customer_id = p_customer
$$;

CREATE PROCEDURE archive_orders(p_before TIMESTAMP)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO orders_archive(id, customer_id, status, created_at)
    SELECT id, customer_id, status, created_at FROM orders WHERE created_at < p_before;
    DELETE FROM orders WHERE created_at < p_before;
END;
$$;

-- Objects in another schema must not leak into the extract of lineage_it
CREATE SCHEMA lineage_it_noise;
CREATE TABLE lineage_it_noise.orders (id INTEGER PRIMARY KEY);
CREATE VIEW lineage_it_noise.leaked AS SELECT id FROM lineage_it.orders;
CREATE FUNCTION lineage_it_noise.leaky() RETURNS BIGINT LANGUAGE sql AS $$ SELECT COUNT(*) FROM lineage_it.customers $$;
