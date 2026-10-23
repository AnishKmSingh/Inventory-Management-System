DROP DATABASE IF EXISTS Inventory;
CREATE DATABASE Inventory;
USE Inventory;
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    role ENUM('admin','staff') DEFAULT 'staff'
);
CREATE TABLE audit_logs (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    table_name VARCHAR(64) NOT NULL,
    record_id INT,
    action ENUM('CREATE', 'UPDATE', 'DELETE') NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE TABLE products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    unit_cost DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    quantity_in_stock INT NOT NULL DEFAULT 0,
    alert_level INT
);
CREATE TABLE suppliers (
    supplier_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    contact_person VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(50)
);
CREATE TABLE customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(50),
    address VARCHAR(200)
);
CREATE TABLE storage_locations (
    location_id INT AUTO_INCREMENT PRIMARY KEY,
    full_address VARCHAR(200)
);
CREATE TABLE inventory_by_location (
    inventory_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    location_id INT NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (location_id) REFERENCES storage_locations(location_id)
);
CREATE TABLE stock_transfers (
    transfer_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    from_location_id INT NOT NULL,
    to_location_id INT NOT NULL,
    transferred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (from_location_id) REFERENCES storage_locations(location_id),
    FOREIGN KEY (to_location_id) REFERENCES storage_locations(location_id)
);
CREATE TABLE stock_transfer_items (
    transfer_item_id INT AUTO_INCREMENT PRIMARY KEY,
    transfer_id INT NOT NULL,
    product_id INT NOT NULL,
    source_inventory_id INT NOT NULL,
    destination_inventory_id INT NOT NULL,
    quantity INT NOT NULL,
    FOREIGN KEY (transfer_id) REFERENCES stock_transfers(transfer_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (source_inventory_id) REFERENCES inventory_by_location(inventory_id),
    FOREIGN KEY (destination_inventory_id) REFERENCES inventory_by_location(inventory_id)
);
CREATE TABLE purchase_orders (
    po_id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id INT NOT NULL,
    user_id INT NOT NULL,
    order_date DATE DEFAULT(CURRENT_DATE),
    status VARCHAR(20) DEFAULT 'Pending',
    notes TEXT,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE TABLE sales_orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    user_id INT NOT NULL,
    order_date DATE DEFAULT (CURRENT_DATE),
    delivery_address VARCHAR(200),
    status VARCHAR(20) DEFAULT 'Pending',
    notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE TABLE purchase_order_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    po_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_cost DECIMAL(10,2) NOT NULL,
    inventory_id INT NOT NULL,
    supplier_storage_location VARCHAR(200),
    FOREIGN KEY (inventory_id) REFERENCES inventory_by_location(inventory_id),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id)
);
CREATE TABLE sales_order_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    inventory_id INT NOT NULL,
    FOREIGN KEY (inventory_id) REFERENCES inventory_by_location(inventory_id),
    FOREIGN KEY (order_id) REFERENCES sales_orders(order_id)
);
CREATE TABLE stock_transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    transaction_type VARCHAR(15) NOT NULL,
    reference_type VARCHAR(30),
    reference_id INT,
    notes TEXT,
    date Varchar(50),
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE TABLE stock_transaction_items (
    transaction_item_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES stock_transactions(transaction_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
CREATE TABLE inventory_lots (
    lot_id INT AUTO_INCREMENT PRIMARY KEY,
    po_item_id INT NOT NULL,
    inventory_id INT NOT NULL,
    product_id INT NOT NULL,
    received_quantity INT NOT NULL,
    remaining_quantity INT NOT NULL,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (po_item_id) REFERENCES purchase_order_items(item_id),
    FOREIGN KEY (inventory_id) REFERENCES inventory_by_location(inventory_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
CREATE TABLE product_history (
    transport_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    lot_id INT NOT NULL,
    supplier_id INT NOT NULL, -- Inbound (Supplier -> Warehouse)
    po_id INT NOT NULL, -- Reference to Purchase Order
    location_id INT NOT NULL, -- Warehouse where it was stored
    source_supply_location VARCHAR(200),
    customer_id INT NOT NULL, -- Outbound (Warehouse -> Customer)
    delivery_address VARCHAR(200) NOT NULL, -- Outbound (Warehouse -> Customer)
    order_id INT NOT NULL, -- Reference to Sales Order
    -- Shipping Metadata
    dispatch_date DATETIME,
    delivery_date DATETIME,
    delivery_status VARCHAR(20),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (lot_id) REFERENCES inventory_lots(lot_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (location_id) REFERENCES storage_locations(location_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id),
    FOREIGN KEY (order_id) REFERENCES sales_orders(order_id)
);

DELIMITER $$
CREATE TRIGGER log_completed_purchase_order
AFTER UPDATE ON purchase_orders
FOR EACH ROW
BEGIN
    DECLARE transaction_id INT;
     IF NOT (OLD.status = 'Completed') AND NEW.status = 'Completed'
        AND EXISTS (SELECT 1 FROM purchase_order_items WHERE po_id = NEW.po_id) THEN
        INSERT INTO stock_transactions (user_id, transaction_type, reference_type, reference_id, date)
        VALUES (NEW.user_id, 'STOCK IN', 'Purchase Order', NEW.po_id, NEW.order_date);
        SET transaction_id = LAST_INSERT_ID();
        INSERT INTO stock_transaction_items (transaction_id, product_id, quantity)
        SELECT transaction_id, ibl.product_id, poi.quantity
        FROM purchase_order_items poi
        JOIN inventory_by_location ibl ON ibl.inventory_id = poi.inventory_id
        WHERE poi.po_id = NEW.po_id;
    END IF;
END$$
CREATE TRIGGER log_reversed_purchase_order
AFTER UPDATE ON purchase_orders
FOR EACH ROW
BEGIN
    DECLARE transaction_id INT;
     IF OLD.status = 'Completed' AND NEW.status IN ('Cancelled', 'Deleted')
        AND EXISTS (SELECT 1 FROM purchase_order_items WHERE po_id = NEW.po_id) THEN
        INSERT INTO stock_transactions (user_id, transaction_type, reference_type, reference_id, notes, date)
        VALUES (NEW.user_id, 'STOCK OUT', 'Purchase Order', NEW.po_id, CONCAT('Reversal: ', NEW.status), CURRENT_DATE);
        SET transaction_id = LAST_INSERT_ID();
        INSERT INTO stock_transaction_items (transaction_id, product_id, quantity)
        SELECT transaction_id, ibl.product_id, poi.quantity
        FROM purchase_order_items poi
        JOIN inventory_by_location ibl ON ibl.inventory_id = poi.inventory_id
        WHERE poi.po_id = NEW.po_id;
    END IF;
END$$
CREATE TRIGGER log_completed_sales_order
AFTER UPDATE ON sales_orders
FOR EACH ROW
BEGIN
    DECLARE transaction_id INT;
     IF NOT (OLD.status = 'Completed') AND NEW.status = 'Completed'
        AND EXISTS (SELECT 1 FROM sales_order_items WHERE order_id = NEW.order_id) THEN
        INSERT INTO stock_transactions (user_id, transaction_type, reference_type, reference_id, date)
        VALUES (NEW.user_id, 'STOCK OUT', 'Sales Order', NEW.order_id, NEW.order_date);
        SET transaction_id = LAST_INSERT_ID();
        INSERT INTO stock_transaction_items (transaction_id, product_id, quantity)
        SELECT transaction_id, ibl.product_id, soi.quantity
        FROM sales_order_items soi
        JOIN inventory_by_location ibl ON ibl.inventory_id = soi.inventory_id
        WHERE soi.order_id = NEW.order_id;
    END IF;
END$$
CREATE TRIGGER log_reversed_sales_order
AFTER UPDATE ON sales_orders
FOR EACH ROW
BEGIN
    DECLARE transaction_id INT;
     IF OLD.status = 'Completed' AND NEW.status IN ('Cancelled', 'Deleted')
        AND EXISTS (SELECT 1 FROM sales_order_items WHERE order_id = NEW.order_id) THEN
        INSERT INTO stock_transactions (user_id, transaction_type, reference_type, reference_id, notes, date)
        VALUES (NEW.user_id, 'STOCK IN', 'Sales Order', NEW.order_id, CONCAT('Reversal: ', NEW.status), CURRENT_DATE);
        SET transaction_id = LAST_INSERT_ID();
        INSERT INTO stock_transaction_items (transaction_id, product_id, quantity)
        SELECT transaction_id, ibl.product_id, soi.quantity
        FROM sales_order_items soi
        JOIN inventory_by_location ibl ON ibl.inventory_id = soi.inventory_id
        WHERE soi.order_id = NEW.order_id;
    END IF;
END$$
CREATE TRIGGER audit_products_insert
AFTER INSERT ON products
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'products', NEW.product_id, 'CREATE',
            CONCAT('Created product: ', NEW.name));
END$$
CREATE TRIGGER audit_products_update
AFTER UPDATE ON products
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'products', NEW.product_id, 'UPDATE',
            CONCAT('Changed product from "', OLD.name, '" to "', NEW.name,
                   '"; stock from ', OLD.quantity_in_stock, ' to ', NEW.quantity_in_stock));
END$$
CREATE TRIGGER audit_products_delete
AFTER DELETE ON products
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'products', OLD.product_id, 'DELETE',
            CONCAT('Deleted product: ', OLD.name));
END$$
CREATE TRIGGER audit_suppliers_insert
AFTER INSERT ON suppliers
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'suppliers', NEW.supplier_id, 'CREATE',
            CONCAT('Created supplier: ', NEW.name));
END$$
CREATE TRIGGER audit_suppliers_update
AFTER UPDATE ON suppliers
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'suppliers', NEW.supplier_id, 'UPDATE',
            CONCAT('Updated supplier: ', OLD.name, ' -> ', NEW.name));
END$$
CREATE TRIGGER audit_suppliers_delete
AFTER DELETE ON suppliers
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'suppliers', OLD.supplier_id, 'DELETE',
            CONCAT('Deleted supplier: ', OLD.name));
END$$
CREATE TRIGGER audit_customers_insert
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'customers', NEW.customer_id, 'CREATE',
            CONCAT('Created customer: ', NEW.name));
END$$
CREATE TRIGGER audit_customers_update
AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'customers', NEW.customer_id, 'UPDATE',
            CONCAT('Updated customer: ', OLD.name, ' -> ', NEW.name));
END$$
CREATE TRIGGER audit_customers_delete
AFTER DELETE ON customers
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'customers', OLD.customer_id, 'DELETE',
            CONCAT('Deleted customer: ', OLD.name));
END$$
CREATE TRIGGER audit_storage_locations_insert
AFTER INSERT ON storage_locations
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'storage_locations', NEW.location_id, 'CREATE',
            CONCAT('Created storage location: ', NEW.full_address));
END$$
CREATE TRIGGER audit_storage_locations_update
AFTER UPDATE ON storage_locations
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'storage_locations', NEW.location_id, 'UPDATE',
            CONCAT('Updated storage location: ', OLD.full_address, ' -> ', NEW.full_address));
END$$
CREATE TRIGGER audit_storage_locations_delete
AFTER DELETE ON storage_locations
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'storage_locations', OLD.location_id, 'DELETE',
            CONCAT('Deleted storage location: ', OLD.full_address));
END$$
CREATE TRIGGER audit_inventory_insert
AFTER INSERT ON inventory_by_location
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'inventory_by_location', NEW.inventory_id, 'CREATE',
            CONCAT('Created inventory entry with stock ', NEW.stock));
END$$
CREATE TRIGGER audit_inventory_update
AFTER UPDATE ON inventory_by_location
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'inventory_by_location', NEW.inventory_id, 'UPDATE',
            CONCAT('Changed stock from ', OLD.stock, ' to ', NEW.stock));
END$$
CREATE TRIGGER audit_inventory_delete
AFTER DELETE ON inventory_by_location
FOR EACH ROW
BEGIN
    IF @audit_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit user is not set';
    END IF;
    INSERT INTO audit_logs (user_id, table_name, record_id, action, details)
    VALUES (@audit_user_id, 'inventory_by_location', OLD.inventory_id, 'DELETE',
            CONCAT('Deleted inventory entry with stock ', OLD.stock));
END$$
DELIMITER ;
