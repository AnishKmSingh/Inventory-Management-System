import mysql.connector
from functools import wraps
from mysql.connector import Error
import hashlib

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Your_MYSQL_Root_Password",
    "database": "Inventory"
}


def transactional(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        self.conn.start_transaction()
        self._in_transaction = True
        try:
            result = method(self, *args, **kwargs)
            self.conn.commit()
            return result
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self._in_transaction = False
    return wrapper


class Database:
    def __init__(self):
        self.conn = mysql.connector.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor(dictionary=True)
        self._in_transaction = False
        self._ensure_order_notes_schema()
        self._ensure_transfer_schema()
        self._ensure_audit_export_action()
        self._ensure_default_admin()   #Login

    def _ensure_order_notes_schema(self):
        for table in ("purchase_orders", "sales_orders"):
            column = self._run(
                """SELECT COUNT(*) AS column_count
                   FROM information_schema.columns
                   WHERE table_schema=%s AND table_name=%s AND column_name='notes'""",
                (DB_CONFIG["database"], table), fetchone=True
            )
            if column["column_count"] == 0:
                self._run(f"ALTER TABLE {table} ADD COLUMN notes TEXT")

    def _ensure_transfer_schema(self):
        self._run(
            """CREATE TABLE IF NOT EXISTS stock_transfers (
                   transfer_id INT AUTO_INCREMENT PRIMARY KEY,
                   user_id INT NOT NULL,
                   from_location_id INT NOT NULL,
                   to_location_id INT NOT NULL,
                   transferred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                   notes TEXT,
                   FOREIGN KEY (user_id) REFERENCES users(user_id),
                   FOREIGN KEY (from_location_id)
                       REFERENCES storage_locations(location_id),
                   FOREIGN KEY (to_location_id)
                       REFERENCES storage_locations(location_id)
               )"""
        )
        self._run(
            """CREATE TABLE IF NOT EXISTS stock_transfer_items (
                   transfer_item_id INT AUTO_INCREMENT PRIMARY KEY,
                   transfer_id INT NOT NULL,
                   product_id INT NOT NULL,
                   source_inventory_id INT NOT NULL,
                   destination_inventory_id INT NOT NULL,
                   quantity INT NOT NULL,
                   FOREIGN KEY (transfer_id)
                       REFERENCES stock_transfers(transfer_id),
                   FOREIGN KEY (product_id) REFERENCES products(product_id),
                   FOREIGN KEY (source_inventory_id)
                       REFERENCES inventory_by_location(inventory_id),
                   FOREIGN KEY (destination_inventory_id)
                       REFERENCES inventory_by_location(inventory_id)
               )"""
        )

    def _run(self, query, params=None, fetch=False, fetchone=False):
        self.cursor.execute(query, params or ())
        if fetch:
            result = self.cursor.fetchall()
            if not self._in_transaction:
                self.conn.commit()
            return result
        if fetchone:
            result = self.cursor.fetchone()
            if not self._in_transaction:
                self.conn.commit()
            return result
        if not self._in_transaction:
            self.conn.commit()
        return self.cursor.lastrowid

    def _set_audit_user(self, user_id):
        if user_id is None:
            raise ValueError("A user is required to record this change")
        self._run("SET @audit_user_id = %s", (user_id,))

    def _ensure_audit_export_action(self):
        column = self._run(
            """SELECT COLUMN_TYPE AS column_type
               FROM information_schema.columns
               WHERE table_schema=%s AND table_name='audit_logs'
                 AND column_name='action'""",
            (DB_CONFIG["database"],), fetchone=True
        )
        if column and "'EXPORT'" not in column["column_type"]:
            self._run(
                """ALTER TABLE audit_logs
                   MODIFY COLUMN action
                   ENUM('CREATE', 'UPDATE', 'DELETE', 'EXPORT') NOT NULL"""
            )

    def _record_audit(self, user_id, table_name, record_id, action, details):
        self._run(
            """INSERT INTO audit_logs
               (user_id, table_name, record_id, action, details)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, table_name, record_id, action, details)
        )

    def record_export(self, user_id, title, path, row_count):
        self._record_audit(
            user_id, "excel_exports", None, "EXPORT",
            f"Exported {row_count} rows from {title} to {path}"
        )

    def get_audit_log(self):
        return self._run(
            """SELECT al.*, u.username AS user_name
               FROM audit_logs al
               JOIN users u ON al.user_id = u.user_id
               ORDER BY al.created_at ASC, al.audit_id ASC""",
            fetch=True
        )


# login 
    @staticmethod
    def _hash(password):
        return hashlib.sha256(password.encode()).hexdigest()

    def _ensure_default_admin(self):
        row = self._run("SELECT COUNT(*) AS c FROM users", fetchone=True)
        if row["c"] == 0:
            self._run(
                "INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                ("admin", self._hash("admin@123"), "admin")
            )

    def authenticate(self, username, password):
        username = username.strip()
        if not username or not password:
            return None
        row = self._run("SELECT * FROM users WHERE username=%s", (username,), fetchone=True)
        if row and row["password_hash"] == self._hash(password):
            return row
        return None

    def create_user(self, username, password):
        username = username.strip()
        if not username or not password:
            raise ValueError("Username and password are required")

        existing = self._run(
            "SELECT user_id FROM users WHERE username=%s",
            (username,),
            fetchone=True
        )
        if existing:
            raise ValueError("That username is already registered")

        return self._run(
            "INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
            (username, self._hash(password), "staff")
        )

    #-----Products------
    def get_products(self, search=""):
        return self._run(
            "SELECT * FROM products WHERE name LIKE %s ORDER BY product_id ASC",
            (f"%{search}%",), fetch=True
        )

    @transactional
    def add_product(self, name, category, unit_cost, unit_price, alert_level, user_id):
        self._set_audit_user(user_id)
        product_id = self._run(
            """INSERT INTO products (name, category, unit_cost, unit_price, alert_level)
               VALUES (%s,%s,%s,%s,%s)""",
            (name, category, unit_cost, unit_price, alert_level)
        )
        return product_id

    @transactional
    def update_product(self, product_id, name, category, unit_cost, unit_price,
                       alert_level, user_id):
        self._set_audit_user(user_id)
        old = self._run("SELECT * FROM products WHERE product_id=%s",
                        (product_id,), fetchone=True)
        if old is None:
            raise ValueError("Product not found")
        self._run(
            """UPDATE products SET name=%s, category=%s, unit_cost=%s, unit_price=%s,
               alert_level=%s
               WHERE product_id=%s""",
            (name, category, unit_cost, unit_price, alert_level, product_id)
        )

    @transactional
    def delete_product(self, product_id, user_id):
        self._set_audit_user(user_id)
        self._run("DELETE FROM products WHERE product_id=%s", (product_id,))

    def low_stock_alert(self):
        return self._run(
            """SELECT * FROM products
               WHERE quantity_in_stock <= alert_level AND quantity_in_stock > 0
               ORDER BY product_id ASC""",
            fetch=True
        )

    def out_of_stock_alert(self):
        return self._run(
            "SELECT * FROM products WHERE quantity_in_stock = 0 ORDER BY product_id ASC",
            fetch=True
        )

    # ---------- suppliers ----------
    def get_suppliers(self, search=""):
        return self._run(
            "SELECT * FROM suppliers WHERE category LIKE %s ORDER BY supplier_id ASC",
            (f"%{search}%",), fetch=True
        )

    @transactional
    def add_supplier(self, name, category, contact_person, email, phone, user_id):
        self._set_audit_user(user_id)
        supplier_id = self._run(
            """INSERT INTO suppliers (name, category, contact_person, email, phone)
               VALUES (%s,%s,%s,%s,%s)""",
            (name, category, contact_person, email, phone)
        )
        return supplier_id

    @transactional
    def delete_supplier(self, supplier_id, user_id):
        self._set_audit_user(user_id)
        self._run("DELETE FROM suppliers WHERE supplier_id=%s", (supplier_id,))

    @transactional
    def update_supplier(self, supplier_id, name, category, contact_person, email, phone, user_id):
        self._set_audit_user(user_id)
        old = self._run("SELECT * FROM suppliers WHERE supplier_id=%s",
                        (supplier_id,), fetchone=True)
        if old is None:
            raise ValueError("Supplier not found")
        self._run(
            """UPDATE suppliers SET name=%s, category=%s, contact_person=%s, email=%s, phone=%s
            WHERE supplier_id=%s""",
            (name, category, contact_person, email, phone, supplier_id)
        )

    # ---------- customers ----------
    def get_customers(self, search=""):
        return self._run(
            "SELECT * FROM customers WHERE name LIKE %s ORDER BY customer_id ASC",
            (f"%{search}%",), fetch=True
        )

    @transactional
    def add_customer(self, name, email, phone, address, user_id):
        self._set_audit_user(user_id)
        customer_id = self._run(
            "INSERT INTO customers (name, email, phone, address) VALUES (%s,%s,%s,%s)",
            (name, email, phone, address)
        )
        return customer_id

    @transactional
    def delete_customer(self, customer_id, user_id):
        self._set_audit_user(user_id)
        self._run("DELETE FROM customers WHERE customer_id=%s", (customer_id,))

    @transactional
    def update_customer(self, customer_id, name, email, phone, address, user_id):
        self._set_audit_user(user_id)
        old = self._run("SELECT * FROM customers WHERE customer_id=%s",
                        (customer_id,), fetchone=True)
        if old is None:
            raise ValueError("Customer not found")
        self._run(
            "UPDATE customers SET name=%s, email=%s, phone=%s, address=%s WHERE customer_id=%s",
            (name, email, phone, address, customer_id)
        )

    # ---------- storage locations ----------
    def get_storage_locations(self, search=""):
        return self._run(
            """SELECT l.location_id, l.full_address,
                      COALESCE(SUM(ibl.stock), 0) AS total_stock
               FROM storage_locations l
               LEFT JOIN inventory_by_location ibl ON l.location_id = ibl.location_id
               WHERE l.full_address LIKE %s
               GROUP BY l.location_id, l.full_address
               ORDER BY l.location_id ASC""",
            (f"%{search}%",), fetch=True
        )

    def get_location_inventory(self, location_id):
        return self._run(
            """SELECT p.name AS product_name, ibl.stock
               FROM inventory_by_location ibl
               JOIN products p ON ibl.product_id = p.product_id
               WHERE ibl.location_id = %s
               ORDER BY p.name ASC""",
            (location_id,), fetch=True
        )

    @transactional
    def add_storage_location(self, full_address, user_id):
        self._set_audit_user(user_id)
        location_id = self._run(
            "INSERT INTO storage_locations (full_address) VALUES (%s)",
            (full_address,)
        )
        return location_id

    @transactional
    def delete_storage_location(self, location_id, user_id):
        self._set_audit_user(user_id)
        self._run("DELETE FROM storage_locations WHERE location_id=%s", (location_id,))

    @transactional
    def update_storage_location(self, location_id, full_address, user_id):
        self._set_audit_user(user_id)
        old = self._run("SELECT * FROM storage_locations WHERE location_id=%s",
                        (location_id,), fetchone=True)
        if old is None:
            raise ValueError("Storage location not found")
        self._run(
            "UPDATE storage_locations SET full_address=%s WHERE location_id=%s",
            (full_address, location_id)
        )

    def get_customer_purchases(self, customer_id):
        return self._run(
            """SELECT so.*, soi.quantity, p.name AS product_name
               FROM sales_orders so
               LEFT JOIN sales_order_items soi ON so.order_id = soi.order_id
               LEFT JOIN inventory_by_location ibl ON soi.inventory_id = ibl.inventory_id
               LEFT JOIN products p ON ibl.product_id = p.product_id
               WHERE so.customer_id = %s
               ORDER BY so.order_date ASC""",
            (customer_id,), fetch=True
        )

    # ---------- items storage locations ----------
    def get_inventory_by_location(self, search=""):
        return self._run(
            """SELECT ibl.*, p.name AS product_name, l.full_address AS location_address
               FROM inventory_by_location ibl
               LEFT JOIN products p ON ibl.product_id = p.product_id
               LEFT JOIN storage_locations l ON ibl.location_id = l.location_id
               WHERE p.name LIKE %s
               ORDER BY ibl.inventory_id ASC""",
            (f"%{search}%",),
            fetch=True
        )

    @transactional
    def add_inventory_by_location(self, product_id, location_id, user_id):
        self._set_audit_user(user_id)
        inventory_id = self._run(
            """INSERT INTO inventory_by_location (product_id, location_id)
               VALUES (%s,%s)""",
            (product_id, location_id)
        )
        return inventory_id

    @transactional
    def delete_inventory_by_location(self, inventory_id, user_id):
        self._set_audit_user(user_id)
        inventory = self._run(
            """SELECT * FROM inventory_by_location WHERE inventory_id=%s""",
            (inventory_id,),
            fetchone=True
        )
        if inventory is None:
            raise ValueError("Inventory entry not found")
        if inventory["stock"] != 0:
            raise ValueError("An inventory entry can only be deleted when its stock is 0")

        self._run("DELETE FROM inventory_by_location WHERE inventory_id=%s", (inventory_id,))

    @transactional
    def update_inventory_by_location(self, inventory_id, stock, user_id):
        self._set_audit_user(user_id)
        old = self._run("SELECT * FROM inventory_by_location WHERE inventory_id=%s",
                        (inventory_id,), fetchone=True)
        if old is None:
            raise ValueError("Inventory entry not found")
        self._run("UPDATE inventory_by_location SET stock=%s WHERE inventory_id=%s",
                  (stock, inventory_id))

    @transactional
    def transfer_stock(self, inventory_id, quantity, current_location_id,
                       new_location_id, user_id):
        self._set_audit_user(user_id)

        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0")
        if current_location_id == new_location_id:
            raise ValueError("Current and new locations must be different")

        source = self._run(
            """SELECT * FROM inventory_by_location
               WHERE inventory_id=%s
               FOR UPDATE""",
            (inventory_id,), fetchone=True
        )
        if source is None:
            raise ValueError("Inventory entry not found")
        if source["location_id"] != current_location_id:
            raise ValueError(
                "The inventory entry is not stored at the current location"
            )
        if source["stock"] < quantity:
            raise ValueError(
                f"Insufficient stock at the current location "
                f"(available: {source['stock']})"
            )

        source_lots = self._run(
            """SELECT il.lot_id, il.po_item_id, il.product_id,
                      il.remaining_quantity, il.received_at
               FROM inventory_lots il
               JOIN purchase_order_items poi ON il.po_item_id = poi.item_id
               JOIN purchase_orders po ON poi.po_id = po.po_id
               WHERE il.inventory_id=%s
                 AND il.product_id=%s
                 AND il.remaining_quantity > 0
                 AND po.status='Completed'
               ORDER BY il.received_at ASC, il.lot_id ASC
               FOR UPDATE""",
            (inventory_id, source["product_id"]), fetch=True
        )
        if sum(lot["remaining_quantity"] for lot in source_lots) < quantity:
            raise ValueError(
                "This stock has no completed purchase source and cannot be transferred"
            )

        destination_location = self._run(
            "SELECT location_id FROM storage_locations WHERE location_id=%s",
            (new_location_id,), fetchone=True
        )
        if destination_location is None:
            raise ValueError("New storage location not found")

        destination = self._run(
            """SELECT inventory_id, stock
               FROM inventory_by_location
               WHERE product_id=%s AND location_id=%s
               ORDER BY inventory_id ASC
               LIMIT 1
               FOR UPDATE""",
            (source["product_id"], new_location_id), fetchone=True
        )

        self._run(
            "UPDATE inventory_by_location SET stock=stock-%s WHERE inventory_id=%s",
            (quantity, inventory_id)
        )
        if destination is None:
            destination_inventory_id = self._run(
                """INSERT INTO inventory_by_location
                   (product_id, location_id, stock)
                   VALUES (%s,%s,%s)""",
                (source["product_id"], new_location_id, quantity)
            )
        else:
            destination_inventory_id = destination["inventory_id"]
            self._run(
                "UPDATE inventory_by_location SET stock=stock+%s WHERE inventory_id=%s",
                (quantity, destination_inventory_id)
            )

        remaining = quantity
        for lot in source_lots:
            if remaining == 0:
                break
            moved_quantity = min(remaining, lot["remaining_quantity"])
            self._run(
                """UPDATE inventory_lots
                   SET remaining_quantity=remaining_quantity-%s
                   WHERE lot_id=%s""",
                (moved_quantity, lot["lot_id"])
            )
            self._run(
                """INSERT INTO inventory_lots
                   (po_item_id, inventory_id, product_id,
                    received_quantity, remaining_quantity, received_at)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    lot["po_item_id"], destination_inventory_id, lot["product_id"],
                    moved_quantity, moved_quantity, lot["received_at"]
                )
            )
            remaining -= moved_quantity

        transfer_id = self._run(
            """INSERT INTO stock_transfers
               (user_id, from_location_id, to_location_id)
               VALUES (%s,%s,%s)""",
            (user_id, current_location_id, new_location_id)
        )
        self._run(
            """INSERT INTO stock_transfer_items
               (transfer_id, product_id, source_inventory_id,
                destination_inventory_id, quantity)
               VALUES (%s,%s,%s,%s,%s)""",
            (transfer_id, source["product_id"], inventory_id,
             destination_inventory_id, quantity)
        )
        return transfer_id
    
    # ---------- purchase orders (stock IN) ----------
    def get_purchase_orders(self):
        return self._run(
            """SELECT po.*, poi.quantity, poi.unit_cost, ibl.product_id,
                      p.name AS product_name, s.name AS supplier_name,
                      l.full_address AS location_address
               FROM purchase_orders po
               LEFT JOIN purchase_order_items poi ON po.po_id = poi.po_id
               LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
               LEFT JOIN inventory_by_location ibl ON poi.inventory_id = ibl.inventory_id
               LEFT JOIN storage_locations l ON ibl.location_id = l.location_id
               LEFT JOIN products p ON ibl.product_id = p.product_id
               WHERE po.status != 'Deleted'
               ORDER BY po.po_id ASC""",
            fetch=True
        )

    @transactional
    def add_purchase_order(self, supplier_id, user_id, note=None):
        self._set_audit_user(user_id)
        po_id = self._run(
            """INSERT INTO purchase_orders
               (supplier_id, user_id, notes)
               VALUES (%s,%s,%s)""",
            (supplier_id, user_id, note or None)
        )
        self._record_audit(
            user_id, "purchase_orders", po_id, "CREATE",
            f"Created purchase order {po_id}"
        )
        return po_id

    @transactional
    def update_purchase_order_note(self, po_id, note, user_id):
        self._set_audit_user(user_id)
        order = self._run(
            "SELECT po_id FROM purchase_orders WHERE po_id=%s",
            (po_id,), fetchone=True
        )
        if order is None:
            raise ValueError("Purchase order not found")
        self._run(
            "UPDATE purchase_orders SET notes=%s WHERE po_id=%s",
            (note or None, po_id)
        )

    @transactional
    def update_po_status(self, po_id, status, user_id):
        self._set_audit_user(user_id)
        orders = self._run(
            """SELECT po.po_id, po.supplier_id, ibl.location_id, po.status, po.user_id,
                      poi.item_id, poi.supplier_storage_location,
                      ibl.product_id, poi.quantity, ibl.inventory_id
               FROM purchase_orders po
               LEFT JOIN purchase_order_items poi ON po.po_id = poi.po_id
               LEFT JOIN inventory_by_location ibl ON poi.inventory_id = ibl.inventory_id
               WHERE po.po_id=%s""",
            (po_id,), fetch=True
        )
        if not orders:
            raise ValueError("Purchase order not found")

        was_completed = orders[0]["status"] == "Completed"
        will_be_completed = status == "Completed"
        changes_stock = was_completed or will_be_completed
        if changes_stock and any(order["product_id"] is None or order["quantity"] is None
                                 for order in orders):
            raise ValueError("Order must contain at least one item")

        if not was_completed and will_be_completed:
            for order in orders:
                self._run(
                    """UPDATE inventory_by_location SET stock = stock + %s
                       WHERE inventory_id = %s""",
                    (order["quantity"], order["inventory_id"])
                )
                self._run(
                    """UPDATE products SET quantity_in_stock = quantity_in_stock + %s
                       WHERE product_id = %s""",
                    (order["quantity"], order["product_id"])
                )
                self._run(
                    """INSERT INTO inventory_lots
                       (po_item_id, inventory_id, product_id, received_quantity, remaining_quantity)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (order["item_id"], order["inventory_id"], order["product_id"],
                     order["quantity"], order["quantity"])
                )

        elif was_completed and not will_be_completed:
            lots = self._run(
                """SELECT lot_id, received_quantity, remaining_quantity
                   FROM inventory_lots
                   WHERE po_item_id IN (
                       SELECT item_id FROM purchase_order_items WHERE po_id=%s
                   )
                   FOR UPDATE""",
                (po_id,), fetch=True
            )
            if not lots or any(lot["remaining_quantity"] != lot["received_quantity"] for lot in lots):
                raise ValueError("This purchase order has stock already used by a completed sale")
            for order in orders:
                self._run(
                    """UPDATE inventory_by_location SET stock = stock - %s
                       WHERE inventory_id = %s""",
                    (order["quantity"], order["inventory_id"])
                )
                self._run(
                    """UPDATE products SET quantity_in_stock = quantity_in_stock - %s
                       WHERE product_id = %s""",
                    (order["quantity"], order["product_id"])
                )
            self._run(
                """DELETE FROM inventory_lots
                   WHERE po_item_id IN (
                       SELECT item_id FROM purchase_order_items WHERE po_id=%s
                   )""",
                (po_id,)
            )

        self._run("UPDATE purchase_orders SET status=%s WHERE po_id=%s", (status, po_id))

    def delete_purchase_order(self, po_id, user_id):
        self.update_po_status(po_id, "Deleted", user_id)

    # ---------- purchased order items (stock IN) ----------
    def get_purchase_order_items(self, po_id=None):
        return self._run(
            """SELECT poi.*, p.name AS product_name, l.full_address AS location_address
               FROM purchase_order_items poi
               JOIN purchase_orders po ON poi.po_id = po.po_id
               LEFT JOIN inventory_by_location ibl ON poi.inventory_id = ibl.inventory_id
               LEFT JOIN products p ON ibl.product_id = p.product_id
               LEFT JOIN storage_locations l ON ibl.location_id = l.location_id
               WHERE po.status <> 'Deleted'
                 AND (%s IS NULL OR poi.po_id = %s)
               ORDER BY poi.item_id ASC""",
            (po_id, po_id), fetch=True
        )
    
    @transactional
    def add_purchase_order_item(self, po_id, quantity, unit_cost, inventory_id,
                                supplier_storage_location, user_id):
        self._set_audit_user(user_id)
        item_id = self._run(
            """INSERT INTO purchase_order_items
               (po_id, quantity, unit_cost, inventory_id, supplier_storage_location)
               VALUES (%s,%s,%s,%s,%s)""",
            (po_id, quantity, unit_cost, inventory_id, supplier_storage_location)
        )
        self._record_audit(
            user_id, "purchase_order_items", item_id, "CREATE",
            f"Added item to purchase order {po_id} with quantity {quantity}"
        )
        return item_id

    @transactional
    def delete_purchase_order_item(self, item_id, user_id):
        self._set_audit_user(user_id)
        item = self._run(
            """SELECT poi.item_id, poi.po_id, poi.quantity, poi.inventory_id,
                      ibl.product_id, po.status
               FROM purchase_order_items poi
               JOIN purchase_orders po ON poi.po_id = po.po_id
               JOIN inventory_by_location ibl ON poi.inventory_id = ibl.inventory_id
               WHERE poi.item_id = %s
               FOR UPDATE""",
            (item_id,), fetchone=True
        )
        if item is None:
            raise ValueError("Purchased item not found")
        if item["status"] == "Completed":
            lots = self._run(
                """SELECT lot_id, received_quantity, remaining_quantity
                   FROM inventory_lots
                   WHERE po_item_id = %s
                   FOR UPDATE""",
                (item_id,), fetch=True
            )
            if not lots or any(
                lot["remaining_quantity"] != lot["received_quantity"] for lot in lots
            ):
                raise ValueError(
                    "This item cannot be deleted because some received stock has already been sold"
                )
            self._run(
                """UPDATE inventory_by_location SET stock = stock - %s
                   WHERE inventory_id = %s""",
                (item["quantity"], item["inventory_id"])
            )
            self._run(
                """UPDATE products SET quantity_in_stock = quantity_in_stock - %s
                   WHERE product_id = %s""",
                (item["quantity"], item["product_id"])
            )
            self._run("DELETE FROM inventory_lots WHERE po_item_id = %s", (item_id,))
        self._run(
            """INSERT INTO audit_logs
               (user_id, table_name, record_id, action, details)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                user_id,
                "purchase_order_items",
                item_id,
                "DELETE",
                f"Deleted purchased item from purchase order {item['po_id']} "
                f"with quantity {item['quantity']}",
            )
        )
        self._run("DELETE FROM purchase_order_items WHERE item_id = %s", (item_id,))

    # ---------- sales orders (stock OUT) ----------
    def get_sales_orders(self):
        return self._run(
            """SELECT so.*, soi.quantity, p.name AS product_name,
                      c.name AS customer_name, l.full_address AS location_address
               FROM sales_orders so
               LEFT JOIN sales_order_items soi ON so.order_id = soi.order_id
               LEFT JOIN customers c ON so.customer_id = c.customer_id
               LEFT JOIN inventory_by_location ibl ON soi.inventory_id = ibl.inventory_id
               LEFT JOIN storage_locations l ON ibl.location_id = l.location_id
               LEFT JOIN products p ON ibl.product_id = p.product_id
               WHERE so.status <> 'Deleted'
               ORDER BY so.order_id ASC""",
            fetch=True
        )

    @transactional
    def add_sales_order(self, customer_id, delivery_address, user_id, note=None):
        self._set_audit_user(user_id)
        order_id = self._run(
            """INSERT INTO sales_orders
               (customer_id, delivery_address, user_id, notes)
               VALUES (%s,%s,%s,%s)""",
            (customer_id, delivery_address, user_id, note or None)
        )
        self._record_audit(
            user_id, "sales_orders", order_id, "CREATE",
            f"Created sales order {order_id}"
        )
        return order_id

    @transactional
    def update_sales_order_note(self, order_id, note, user_id):
        self._set_audit_user(user_id)
        order = self._run(
            "SELECT order_id FROM sales_orders WHERE order_id=%s",
            (order_id,), fetchone=True
        )
        if order is None:
            raise ValueError("Sales order not found")
        self._run(
            "UPDATE sales_orders SET notes=%s WHERE order_id=%s",
            (note or None, order_id)
        )

    @transactional
    def update_so_status(self, order_id, status, user_id):
        self._set_audit_user(user_id)
        orders = self._run(
            """SELECT so.order_id, so.customer_id, so.delivery_address, ibl.location_id,
                      so.user_id, so.status, ibl.product_id, soi.quantity, ibl.inventory_id
               FROM sales_orders so
               LEFT JOIN sales_order_items soi ON so.order_id = soi.order_id
               LEFT JOIN inventory_by_location ibl ON soi.inventory_id = ibl.inventory_id
               WHERE so.order_id=%s""",
            (order_id,), fetch=True
        )
        if not orders:
            raise ValueError("Sales order not found")

        was_completed = orders[0]["status"] == "Completed"
        will_be_completed = status == "Completed"
        changes_stock = was_completed or will_be_completed
        if changes_stock and any(order["product_id"] is None or order["quantity"] is None
                                 for order in orders):
            raise ValueError("Order must contain at least one item")

        if not was_completed and will_be_completed:
            self._run(
                """DELETE FROM product_history
                   WHERE order_id=%s AND delivery_status IN ('Cancelled', 'Deleted')""",
                (order_id,)
            )
            for order in orders:
                product = self._run(
                    "SELECT quantity_in_stock FROM products WHERE product_id=%s",
                    (order["product_id"],),
                    fetchone=True
                )
                location = self._run(
                    "SELECT stock FROM inventory_by_location WHERE inventory_id=%s",
                    (order["inventory_id"],),
                    fetchone=True
                )
                if product["quantity_in_stock"] < order["quantity"]:
                    raise ValueError("Not enough total stock")
                if location["stock"] < order["quantity"]:
                    raise ValueError("Not enough stock at storage location")

            allocations = []
            for order in orders:
                lots = self._run(
                    """SELECT il.lot_id, il.remaining_quantity, poi.po_id,
                              poi.supplier_storage_location, po.supplier_id
                       FROM inventory_lots il
                       JOIN purchase_order_items poi ON il.po_item_id = poi.item_id
                       JOIN purchase_orders po ON poi.po_id = po.po_id
                       WHERE il.inventory_id=%s AND il.product_id=%s
                         AND il.remaining_quantity > 0 AND po.status='Completed'
                       ORDER BY il.received_at ASC, il.lot_id ASC
                       FOR UPDATE""",
                    (order["inventory_id"], order["product_id"]), fetch=True
                )
                remaining = order["quantity"]
                for lot in lots:
                    if remaining == 0:
                        break
                    quantity = min(remaining, lot["remaining_quantity"])
                    allocations.append((order, lot, quantity))
                    remaining -= quantity
                if remaining:
                    raise ValueError(
                        "Some stock has no completed purchase source. Complete a purchase order first."
                    )

            for order in orders:
                self._run(
                    """UPDATE inventory_by_location SET stock = stock - %s
                       WHERE inventory_id = %s""",
                    (order["quantity"], order["inventory_id"])
                )
                self._run(
                    """UPDATE products SET quantity_in_stock = quantity_in_stock - %s
                       WHERE product_id = %s""",
                    (order["quantity"], order["product_id"])
                )
            for order, lot, quantity in allocations:
                self._run(
                    "UPDATE inventory_lots SET remaining_quantity = remaining_quantity - %s "
                    "WHERE lot_id=%s",
                    (quantity, lot["lot_id"])
                )
                self._run(
                    """INSERT INTO product_history
                       (product_id, quantity, lot_id, supplier_id, po_id, location_id,
                        source_supply_location, customer_id, delivery_address, order_id,
                        dispatch_date, delivery_status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s)""",
                    (order["product_id"], quantity, lot["lot_id"], lot["supplier_id"],
                     lot["po_id"], order["location_id"], lot["supplier_storage_location"],
                     order["customer_id"], order["delivery_address"], order_id, status)
                )

        elif was_completed and not will_be_completed:
            product_history_rows = self._run(
                """SELECT lot_id, quantity FROM product_history
                   WHERE order_id=%s FOR UPDATE""",
                (order_id,), fetch=True
            )
            for order in orders:
                self._run(
                    """UPDATE inventory_by_location SET stock = stock + %s
                    WHERE inventory_id = %s""",
                    (order["quantity"], order["inventory_id"])
                )
                self._run(
                    """UPDATE products SET quantity_in_stock = quantity_in_stock + %s
                    WHERE product_id = %s""",
                    (order["quantity"], order["product_id"])
                )
            for product_history in product_history_rows:
                self._run(
                    "UPDATE inventory_lots SET remaining_quantity = remaining_quantity + %s "
                    "WHERE lot_id=%s",
                    (product_history["quantity"], product_history["lot_id"])
                )
            self._run(
                "UPDATE product_history SET delivery_status=%s WHERE order_id=%s",
                (status, order_id)
            )
        self._run("UPDATE sales_orders SET status=%s WHERE order_id=%s", (status, order_id))
        
    def delete_sales_order(self, order_id, user_id):
        self.update_so_status(order_id, "Deleted", user_id)

    # ---------- sales order items (stock OUT) ----------
    def get_sales_order_items(self, order_id=None):
        return self._run(
            """SELECT soi.*, p.name AS product_name, l.full_address AS location_address
               FROM sales_order_items soi
               JOIN sales_orders so ON soi.order_id = so.order_id
               LEFT JOIN inventory_by_location ibl ON soi.inventory_id = ibl.inventory_id
               LEFT JOIN products p ON ibl.product_id = p.product_id
               LEFT JOIN storage_locations l ON ibl.location_id = l.location_id
               WHERE so.status <> 'Deleted'
                 AND (%s IS NULL OR soi.order_id = %s)
               ORDER BY soi.item_id ASC""",
            (order_id, order_id), fetch=True
        )

    @transactional
    def add_sales_order_item(self, order_id, quantity, unit_price, inventory_id,
                             user_id):
        self._set_audit_user(user_id)
        item_id = self._run(
            """INSERT INTO sales_order_items
               (order_id, quantity, unit_price, inventory_id)
               VALUES (%s,%s,%s,%s)""",
            (order_id, quantity, unit_price, inventory_id)
        )
        self._record_audit(
            user_id, "sales_order_items", item_id, "CREATE",
            f"Added item to sales order {order_id} with quantity {quantity}"
        )
        return item_id

    @transactional
    def delete_sales_order_item(self, item_id, user_id):
        self._set_audit_user(user_id)
        item = self._run(
            """SELECT soi.item_id, soi.order_id, soi.quantity, soi.inventory_id,
                      ibl.product_id, ibl.location_id, so.status
               FROM sales_order_items soi
               JOIN sales_orders so ON soi.order_id = so.order_id
               JOIN inventory_by_location ibl ON soi.inventory_id = ibl.inventory_id
               WHERE soi.item_id = %s
               FOR UPDATE""",
            (item_id,), fetchone=True
        )
        if item is None:
            raise ValueError("Sold item not found")
        if item["status"] == "Completed":
            product_history_rows = self._run(
                """SELECT lot_id, quantity
                   FROM product_history
                   WHERE order_id = %s AND product_id = %s AND location_id = %s
                   FOR UPDATE""",
                (item["order_id"], item["product_id"], item["location_id"]),
                fetch=True
            )
            if sum(row["quantity"] for row in product_history_rows) != item["quantity"]:
                raise ValueError(
                    "This item cannot be deleted because its stock movement is incomplete"
                )
            for row in product_history_rows:
                self._run(
                    """UPDATE inventory_lots
                       SET remaining_quantity = remaining_quantity + %s
                       WHERE lot_id = %s""",
                    (row["quantity"], row["lot_id"])
                )
            self._run(
                """UPDATE inventory_by_location SET stock = stock + %s
                   WHERE inventory_id = %s""",
                (item["quantity"], item["inventory_id"])
            )
            self._run(
                """UPDATE products SET quantity_in_stock = quantity_in_stock + %s
                   WHERE product_id = %s""",
                (item["quantity"], item["product_id"])
            )
            self._run(
                """DELETE FROM product_history
                   WHERE order_id = %s AND product_id = %s AND location_id = %s""",
                (item["order_id"], item["product_id"], item["location_id"])
            )
        self._run(
            """INSERT INTO audit_logs
               (user_id, table_name, record_id, action, details)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                user_id,
                "sales_order_items",
                item_id,
                "DELETE",
                f"Deleted sold item from sales order {item['order_id']} "
                f"with quantity {item['quantity']}",
            )
        )
        self._run("DELETE FROM sales_order_items WHERE item_id = %s", (item_id,))

    # ---------- product history ----------
    def get_product_history(self):
        return self._run(
            """SELECT tr.*, p.name AS product_name, s.name AS supplier_name,
                      sl.full_address AS storage_address, c.name AS customer_name
               FROM product_history tr
               JOIN products p ON tr.product_id = p.product_id
               JOIN suppliers s ON tr.supplier_id = s.supplier_id
               JOIN storage_locations sl ON tr.location_id = sl.location_id
               JOIN customers c ON tr.customer_id = c.customer_id
               ORDER BY tr.transport_id ASC""",
            fetch=True
        )

    #----------- Pending Purchase and Sales order Functrion -------------
    def get_pending_purchase_orders(self):
        self.cursor.execute(
            """SELECT po.*, s.name AS supplier_name,
                     poi.supplier_storage_location
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.supplier_id
            LEFT JOIN purchase_order_items poi ON po.po_id = poi.po_id
            WHERE po.status = 'Pending'
            ORDER BY po.po_id ASC"""
        )
        return self.cursor.fetchall()

    def get_pending_sales_orders(self):
        self.cursor.execute(
            """SELECT so.*, c.name AS customer_name
            FROM sales_orders so
            JOIN customers c ON so.customer_id = c.customer_id
            WHERE so.status = 'Pending'
            ORDER BY so.order_id ASC"""
        )
        return self.cursor.fetchall()

    # ---------- Transaction log ----------
    def get_transaction_log(self):
        return self._run(
            """SELECT sti.*, p.name AS product_name, sti.quantity AS item_quantity, u.username AS user_name, st.* 
               FROM stock_transaction_items sti
               LEFT JOIN stock_transactions st ON sti.transaction_id = st.transaction_id
               LEFT JOIN products p ON sti.product_id = p.product_id
               LEFT JOIN users u ON st.user_id = u.user_id
               ORDER BY st.transaction_id ASC, sti.transaction_item_id ASC""",
            fetch=True
        )

    def get_transfer_log(self):
        return self._run(
            """SELECT st.transfer_id, st.transferred_at, st.notes,
                      sti.quantity, p.name AS product_name,
                      u.username AS user_name,
                      source.full_address AS source_location,
                      destination.full_address AS destination_location
               FROM stock_transfers st
               JOIN stock_transfer_items sti ON sti.transfer_id = st.transfer_id
               JOIN products p ON p.product_id = sti.product_id
               JOIN users u ON u.user_id = st.user_id
               JOIN storage_locations source
                    ON source.location_id = st.from_location_id
               JOIN storage_locations destination
                    ON destination.location_id = st.to_location_id
               ORDER BY st.transferred_at DESC, st.transfer_id DESC,
                        sti.transfer_item_id ASC""",
            fetch=True
        )

    # ---------- dashboard ----------
    def dashboard_stats(self):
        total_products = self._run("SELECT COUNT(*) AS c FROM products", fetchone=True)["c"]
        total_value = self._run(
            "SELECT COALESCE(SUM(unit_price*quantity_in_stock),0) AS v FROM products", fetchone=True
        )["v"]
        low_stock = self._run(
            "SELECT COUNT(*) AS c FROM products WHERE quantity_in_stock <= alert_level AND quantity_in_stock > 0",
            fetchone=True
        )["c"]
        out_of_stock = self._run(
            "SELECT COUNT(*) AS c FROM products WHERE quantity_in_stock = 0", fetchone=True
        )["c"]
        pending_po = self._run(
            "SELECT COUNT(*) AS c FROM purchase_orders WHERE status = 'Pending'", fetchone=True
        )["c"]
        pending_so = self._run(
            "SELECT COUNT(*) AS c FROM sales_orders WHERE status = 'Pending'", fetchone=True
        )["c"]
        return {
            "total_products": total_products, "total_value": total_value,
            "low_stock": low_stock, "out_of_stock": out_of_stock,
            "pending_po": pending_po, "pending_so": pending_so
        }

    def dashboard_extra(self):
            locations = self._run(
                "SELECT COUNT(*) AS c FROM storage_locations", fetchone=True)["c"]
            val = self._run(
                """SELECT COALESCE(SUM(ibl.stock * p.unit_cost), 0) AS cost,
                        COALESCE(SUM(ibl.stock * p.unit_price), 0) AS retail
                FROM inventory_by_location ibl
                JOIN products p ON ibl.product_id = p.product_id""",
                fetchone=True)
            revenue = self._run(
                """SELECT COALESCE(SUM(soi.quantity * soi.unit_price), 0) AS v
                FROM sales_order_items soi
                JOIN sales_orders so ON soi.order_id = so.order_id
                WHERE so.status = 'Completed'""",
                fetchone=True)["v"]
            cogs = self._run(
                """SELECT COALESCE(SUM(ph.quantity * poi.unit_cost), 0) AS v
                FROM product_history ph
                JOIN sales_orders so ON ph.order_id = so.order_id
                JOIN inventory_lots il ON ph.lot_id = il.lot_id
                JOIN purchase_order_items poi ON il.po_item_id = poi.item_id
                WHERE so.status = 'Completed'""",
                fetchone=True)["v"]

            cost, retail = float(val["cost"]), float(val["retail"])
            revenue, cogs = float(revenue), float(cogs)
            margin = retail - cost
            profit = revenue - cogs
            return {
                "locations": locations,
                "cost_basis": cost, "retail_value": retail,
                "gross_margin": margin,
                "margin_pct": (margin / retail * 100) if retail else 0,
                "revenue": revenue, "cogs": cogs, "gross_profit": profit,
                "profit_pct": (profit / revenue * 100) if revenue else 0,
            }
    
    def close(self):
        self.cursor.close()
        self.conn.close()
