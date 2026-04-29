-- =============================================================
--  E-Commerce Schema — DDL Lineage Example
--  Dialect: PostgreSQL
-- =============================================================

CREATE TABLE users (
    id         SERIAL PRIMARY KEY,
    email      VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE categories (
    id        SERIAL PRIMARY KEY,
    name      VARCHAR(100) NOT NULL,
    parent_id INTEGER REFERENCES categories(id)   -- self-referential hierarchy
);

CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    price       DECIMAL(10,2) NOT NULL,
    stock       INTEGER DEFAULT 0,
    category_id INTEGER REFERENCES categories(id)
);

CREATE TABLE orders (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    status     VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id)   REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE payments (
    id       SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    amount   DECIMAL(10,2),
    paid_at  TIMESTAMP
);

CREATE TABLE reports (
    id          SERIAL PRIMARY KEY,
    period      DATE,
    revenue     DECIMAL(12,2),
    order_count INTEGER
);

-- ─── Views ──────────────────────────────────────────────────

CREATE VIEW active_orders AS
    SELECT o.id, o.status, u.email, o.created_at
    FROM   orders o
    JOIN   users  u ON o.user_id = u.id
    WHERE  o.status IN ('pending', 'processing');

CREATE MATERIALIZED VIEW product_sales AS
    SELECT p.id,
           p.name,
           SUM(oi.quantity)               AS total_sold,
           SUM(oi.quantity * oi.unit_price) AS revenue
    FROM   products    p
    JOIN   order_items oi ON p.id = oi.product_id
    GROUP  BY p.id, p.name;

-- ─── Functions ──────────────────────────────────────────────

CREATE OR REPLACE FUNCTION process_order(p_order_id INT)
RETURNS VOID AS $$
BEGIN
    -- Record payment (INSERT with column-level lineage)
    INSERT INTO payments(order_id, amount, paid_at)
    SELECT order_id,
           SUM(quantity * unit_price),
           NOW()
    FROM   order_items
    WHERE  order_id = p_order_id
    GROUP  BY order_id;

    -- Mark order as paid
    UPDATE orders SET status = 'paid' WHERE id = p_order_id;

    -- Reduce stock
    UPDATE products
    SET    stock = stock - oi.quantity
    FROM   order_items oi
    WHERE  oi.order_id   = p_order_id
    AND    oi.product_id = products.id;
END;
$$ LANGUAGE plpgsql;

-- ─── Procedures ─────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE gen_monthly_report(p_month DATE)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO reports(period, revenue, order_count)
    SELECT DATE_TRUNC('month', p.paid_at),
           SUM(p.amount),
           COUNT(o.id)
    FROM   payments p
    JOIN   orders   o ON p.order_id = o.id
    WHERE  DATE_TRUNC('month', p.paid_at) = DATE_TRUNC('month', p_month)
    GROUP  BY 1;
END;
$$;
