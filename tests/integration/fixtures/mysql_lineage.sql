-- Test schema for the MySQL connector integration tests.
-- Idempotent: recreates only the lineage_it / lineage_it_noise databases.
-- Routines use BEGIN … END without DELIMITER; the test splits statements with
-- ddl_lineage's block-aware splitter.

DROP DATABASE IF EXISTS lineage_it_noise;
DROP DATABASE IF EXISTS lineage_it;
CREATE DATABASE lineage_it;
USE lineage_it;

CREATE TABLE customers (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    email   VARCHAR(255) NOT NULL UNIQUE,
    country CHAR(2)
) ENGINE=InnoDB;

CREATE TABLE products (
    id    INT AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(200) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    stock INT NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE orders (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'new',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_id   INT NOT NULL,
    line_no    INT NOT NULL,
    product_id INT NOT NULL,
    quantity   INT NOT NULL,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB;

-- Composite foreign key
CREATE TABLE item_returns (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    line_no  INT NOT NULL,
    reason   TEXT,
    CONSTRAINT fk_returns_item FOREIGN KEY (order_id, line_no) REFERENCES order_items(order_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE payments (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    amount   DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_payments_order FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB;

CREATE TABLE daily_report (
    day   DATE PRIMARY KEY,
    total DECIMAL(14,2) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders_archive (
    id          INT PRIMARY KEY,
    customer_id INT NOT NULL,
    status      VARCHAR(20) NOT NULL,
    created_at  DATETIME NOT NULL
) ENGINE=InnoDB;

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

-- Routines
CREATE PROCEDURE process_order(IN p_order_id INT)
BEGIN
    INSERT INTO payments(order_id, amount)
    SELECT oi.order_id, SUM(oi.quantity * p.price)
    FROM order_items oi
    JOIN products p ON p.id = oi.product_id
    WHERE oi.order_id = p_order_id
    GROUP BY oi.order_id;

    UPDATE products p
    JOIN order_items oi ON oi.product_id = p.id
    SET p.stock = p.stock - oi.quantity
    WHERE oi.order_id = p_order_id;

    IF ROW_COUNT() > 0 THEN
        UPDATE orders SET status = 'paid' WHERE id = p_order_id;
    END IF;
END;

CREATE PROCEDURE build_daily_report(IN p_day DATE)
BEGIN
    CREATE TEMPORARY TABLE stage_sales AS
        SELECT o.id, oi.quantity * p.price AS amount
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        WHERE DATE(o.created_at) = p_day;

    INSERT INTO daily_report(day, total)
    SELECT p_day, COALESCE(SUM(amount), 0) FROM stage_sales;

    DROP TEMPORARY TABLE stage_sales;
END;

CREATE FUNCTION customer_count() RETURNS BIGINT
READS SQL DATA
RETURN (SELECT COUNT(*) FROM customers);

CREATE FUNCTION orders_of(p_customer INT) RETURNS BIGINT
READS SQL DATA
BEGIN
    DECLARE n BIGINT;
    SELECT COUNT(*) INTO n FROM orders WHERE customer_id = p_customer;
    RETURN n;
END;

CREATE PROCEDURE archive_orders(IN p_before DATETIME)
BEGIN
    INSERT INTO orders_archive(id, customer_id, status, created_at)
    SELECT id, customer_id, status, created_at FROM orders WHERE created_at < p_before;
    DELETE FROM orders WHERE created_at < p_before;
END;

-- Objects in another database must not leak into the extract of lineage_it
CREATE DATABASE lineage_it_noise;
CREATE TABLE lineage_it_noise.orders (id INT PRIMARY KEY);
CREATE VIEW lineage_it_noise.leaked AS SELECT id FROM lineage_it.orders;
CREATE FUNCTION lineage_it_noise.leaky() RETURNS BIGINT READS SQL DATA RETURN (SELECT COUNT(*) FROM lineage_it.customers);
