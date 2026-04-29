-- =============================================================
--  Multi-Dialect Example — MySQL / MariaDB style
-- =============================================================

CREATE TABLE `customers` (
  `id`         INT          NOT NULL AUTO_INCREMENT,
  `name`       VARCHAR(100) NOT NULL,
  `email`      VARCHAR(255) NOT NULL UNIQUE,
  PRIMARY KEY (`id`)
);

CREATE TABLE `product_catalog` (
  `id`         INT           NOT NULL AUTO_INCREMENT,
  `sku`        VARCHAR(50)   NOT NULL UNIQUE,
  `title`      VARCHAR(255)  NOT NULL,
  `price`      DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (`id`)
);

CREATE TABLE `cart` (
  `id`          INT NOT NULL AUTO_INCREMENT,
  `customer_id` INT NOT NULL,
  `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  FOREIGN KEY (`customer_id`) REFERENCES `customers`(`id`) ON DELETE CASCADE
);

CREATE TABLE `cart_items` (
  `cart_id`    INT NOT NULL,
  `product_id` INT NOT NULL,
  `qty`        INT NOT NULL DEFAULT 1,
  PRIMARY KEY (`cart_id`, `product_id`),
  FOREIGN KEY (`cart_id`)    REFERENCES `cart`(`id`),
  FOREIGN KEY (`product_id`) REFERENCES `product_catalog`(`id`)
);

-- MySQL stored procedure (BEGIN…END without dollar-quoting)
CREATE PROCEDURE checkout(IN p_cart_id INT, IN p_customer_id INT)
BEGIN
  INSERT INTO orders(customer_id, total, created_at)
  SELECT p_customer_id, SUM(ci.qty * pc.price), NOW()
  FROM   cart_items ci
  JOIN   product_catalog pc ON ci.product_id = pc.id
  WHERE  ci.cart_id = p_cart_id;

  DELETE FROM cart_items WHERE cart_id = p_cart_id;
  DELETE FROM cart       WHERE id       = p_cart_id;
END;
