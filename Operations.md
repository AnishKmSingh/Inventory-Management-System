# Inventory Management System: Operations and Functionalities

This document describes the operations currently supported by the desktop application in [`app.py`](./app.py) and the database layer in [`backend.py`](./backend.py).

## 1. Authentication and Users

### Supported operations

- Log in with a username and password.
- Create a new staff account from the Sign Up window.
- Reject blank credentials and invalid login details.
- Reject duplicate usernames.
- Hash passwords before storing and comparing them.
- Automatically create the default administrator if the `users` table is empty.
- Log out and return to the login window.

### Roles

- `admin` can access all application modules, including Product History, Transaction Log, and Audit Log.
- `staff` can use operational modules but cannot access the three administrator-only log/history pages.
- Role checks are applied both while building navigation and when opening protected pages.

## 2. Dashboard

The dashboard displays:

- Total number of products.
- Estimated inventory value based on unit price and quantity in stock.
- Number of low-stock products.
- Number of out-of-stock products.
- Number of pending purchase orders.
- Number of pending sales orders.
- Quick navigation to the main modules.
- Number of storage locations.
- Total inventory cost basis.
- Total retail value.
- Unrealized gross margin and margin percentage.
- Completed-order net sales revenue.
- Cost of goods sold (COGS).
- Realized gross profit and profit percentage.

Dashboard financial metrics are calculated from current inventory values and completed sales orders. Inventory valuation uses product cost and selling price; profitability uses completed sales revenue and the cost of the inventory lots allocated to those sales.

## 3. Product Operations

The Products page supports:

- Add a product with name, category, unit cost, unit price, and alert level.
- Edit product details.
- Delete a product when database relationships allow it.
- Search products by name.
- View product ID, name, category, cost, price, quantity, and alert level.
- Calculate low-stock and out-of-stock conditions from current quantity.
- Export the displayed product table to Excel.

## 4. Supplier Operations

The Suppliers page supports:

- Add suppliers.
- Edit supplier records.
- Delete suppliers when they are not blocked by related records.
- Search suppliers by category.
- Store supplier name, category, contact person, email, and phone.
- Link suppliers to purchase orders.
- Export the displayed supplier table to Excel.

## 5. Customer Operations

The Customers page supports:

- Add customers.
- Edit customer records.
- Delete customers when database relationships allow it.
- Search customers by name.
- Store customer name, email, phone, and address.
- Link customers to sales orders.
- Double-click a customer to view that customer's purchase history.
- Export the displayed customer table to Excel.

## 6. Storage Location Operations

The Storage Locations page supports:

- Add storage locations.
- Edit location addresses.
- Delete locations when database relationships allow it.
- Search locations by address.
- View total stock at each location.
- Double-click a location to view its products and quantities.
- Export the displayed storage-location table to Excel.

## 7. Inventory-by-Location Operations

The Items in Storage page supports:

- Add a product/location inventory entry.
- View inventory ID, product, storage location, and stock.
- Search inventory by product name.
- Delete an inventory entry only when its stock is zero.
- Validate references before deleting an entry.
- Transfer stock to another storage location.
- Export the displayed inventory table to Excel.

Inventory stock is represented at both levels:

- `inventory_by_location.stock` tracks the quantity at a particular location.
- `products.quantity_in_stock` tracks the product's total quantity across locations.

## 8. Stock Transfers

The Transfer Stock operation:

- Takes an inventory ID, quantity, current location, and new location.
- Rejects zero or negative quantities.
- Rejects transfers to the same location.
- Verifies that the inventory row belongs to the stated source location.
- Verifies sufficient stock at the source.
- Verifies that the destination location exists.
- Reuses an existing destination inventory row or creates one.
- Deducts stock from the source and adds it to the destination.
- Preserves inventory-lot information while moving stock.
- Creates a stock transfer and transfer-item record with the acting user and locations.
- Makes the transfer available in the administrator-only Transfer Log.

## 9. Purchase Orders: Incoming Stock

The Purchase Orders page supports:

- Create a purchase order for a supplier.
- Add or update purchase order notes.
- Mark an order as `Completed`.
- Mark an order as `Cancelled`.
- Delete an order, represented by the `Deleted` status.
- View purchase order ID, supplier, date, status, and notes.
- Export the displayed purchase-order table to Excel.

The Purchased Items page supports:

- Add an item to a purchase order.
- Search purchased items by purchase order ID.
- Record quantity, unit cost, inventory ID, and supplier/source location.
- Delete a purchased item.
- View product, supply location, storage location, quantity, and cost.
- Record CREATE and DELETE changes in the audit log.
- Export the displayed purchased-items table to Excel.

### Purchase completion behavior

When a purchase order is completed:

1. Each item increases stock at its selected inventory location.
2. The related product's total quantity increases.
3. An `inventory_lots` row is created for each received item.
4. A stock-in transaction is created by the database trigger.
5. The order and item changes are available to the audit trail.

### Purchase reversal behavior

When a completed purchase is cancelled or deleted:

- The system checks that the received stock has not already been consumed by a completed sale.
- If safe, it removes the received quantity from location and product totals.
- It removes the corresponding inventory lots.
- The database trigger records the reversal as a stock-out transaction.

## 10. Sales Orders: Outgoing Stock

The Sales Orders page supports:

- Create a sales order for a customer.
- Store a delivery address.
- Add or update sales order notes.
- Mark an order as `Completed`.
- Mark an order as `Cancelled`.
- Delete an order, represented by the `Deleted` status.
- View order ID, customer, date, status, delivery address, and notes.
- Export the displayed sales-order table to Excel.

The Sold Items page supports:

- Add an item to a sales order.
- Search sold items by sales order ID.
- Record quantity, unit price, and inventory ID.
- Delete a sold item.
- View product, storage location, quantity, and selling price.
- Record CREATE and DELETE changes in the audit log.
- Export the displayed sold-items table to Excel.

### Sales completion behavior

When a sales order is completed:

1. The system checks total product stock.
2. It checks stock at each selected storage location.
3. It requires the stock to originate from completed purchase orders.
4. It allocates inventory lots in receipt order.
5. It decreases location stock and total product stock.
6. It decreases the remaining quantity in each consumed lot.
7. It creates product-history rows containing supplier, purchase, location, customer, delivery, lot, and order information.
8. The database trigger records a stock-out transaction.

### Sales reversal behavior

When a completed sale is cancelled or deleted:

- The system restores the sold quantity to the location and product totals.
- It restores the quantity to the related inventory lots.
- It updates product-history delivery status.
- It prevents unsafe changes when the required stock-movement records are incomplete.

## 11. Order Statuses and Pending Views

Purchase and sales orders use these statuses:

- `Pending` - Order has been created but not completed.
- `Completed` - The order changes inventory stock.
- `Cancelled` - A completed order can be reversed when safe.
- `Deleted` - The order is retained as a status for record and relationship handling rather than being silently removed.

The application provides separate pages for:

- Pending purchase orders.
- Pending sales orders.

Pending-order tables can be exported to Excel.

## 12. Low-Stock and Out-of-Stock Monitoring

### Low Stock

Shows products where:

```text
quantity_in_stock <= alert_level
and quantity_in_stock > 0
```

### Out of Stock

Shows products where:

```text
quantity_in_stock = 0
```

These views support replenishment planning and warehouse monitoring.

Low-stock and out-of-stock tables can be exported to Excel.

## 13. Product History

Product History is available to administrators and records the movement of goods from supplier through storage and onward to customers.

The history can include:

- Product and quantity.
- Inventory lot.
- Supplier and purchase order.
- Storage location.
- Source supply location.
- Customer and delivery address.
- Sales order.
- Dispatch date.
- Delivery date.
- Delivery status.

Administrators can export the displayed product-history table to Excel.

## 14. Transaction Log

Transaction Log is available to administrators and displays stock movement records, including:

- Stock-in and stock-out transaction type.
- Related purchase or sales reference.
- Product and item quantity.
- User who performed the related operation.
- Transaction date and notes.

MySQL triggers create stock transaction records when purchase or sales orders change inventory.

Administrators can export the transaction log and the separate transfer log to Excel.

### Transfer Log

The Transfer Log records:

- Transfer ID.
- Product and quantity.
- Source location.
- Destination location.
- User who performed the transfer.
- Transfer timestamp.

## 15. Audit Log

Audit Log is available to administrators and records:

- Audit ID.
- Username responsible for the change.
- Action (`CREATE`, `UPDATE`, or `DELETE`).
- Table name.
- Record ID.
- Operation details.
- Timestamp.
- Excel export actions, including export title, file path, and number of exported rows.

The application records audited changes for products, suppliers, customers, storage locations, inventory, orders, and order items. Purchase/sales order creation and purchase/sales item additions and deletions are explicitly recorded, while database triggers and transaction logic maintain the related stock history. Administrators can export the audit table to Excel.

## 16. Database and Integrity Features

- MySQL foreign keys connect users, products, suppliers, customers, locations, orders, items, lots, and history.
- Parameterized SQL queries are used for database values.
- Stock-changing methods use transactions.
- Failed operations roll back rather than leaving partial stock updates.
- Completed orders cannot be completed without items.
- Sales cannot consume stock that has no completed purchase source.
- Purchase reversals are blocked if the received stock has already been used in a completed sale.
- Inventory entries with nonzero stock cannot be deleted.
- Product, supplier, customer, and location deletion is subject to foreign-key constraints.
- The backend checks and creates order-note columns and transfer tables at startup when necessary.
- The backend updates the `audit_logs.action` enum to include `EXPORT` when necessary.

## 17. Excel Export and Presentation Features

- Export supported table data to `.xlsx` files using `openpyxl`.
- Include column headers and all rows currently shown in the table.
- Format worksheet headers with bold white text and a colored fill.
- Adjust worksheet column widths based on content.
- Use timestamped default filenames.
- Handle empty tables with a user-facing message.
- Report file-save permission errors when the target workbook is open.
- Record successful exports in the audit log.
- Switch between light and dark themes without leaving the current page.
- Apply theme-aware colors to tables and dashboard panels.
- Highlight selected table rows for easier navigation.

## 18. Main GUI Modules

The navigation menu contains:

1. Dashboard
2. Products
3. Suppliers
4. Customers
5. Storage Locations
6. Items in Storage
7. Purchase Orders
8. Purchased Items
9. Sales Orders
10. Sold Items
11. Low Stock
12. Out of Stock
13. Pending Purchases
14. Pending Sales
15. Product History (admin only)
16. Transaction Log and Transfer Log (admin only)
17. Audit Log (admin only)

## 19. End-to-End Workflow

1. Log in as an administrator or staff user.
2. Add products, suppliers, customers, and storage locations.
3. Create an inventory-by-location entry for each product/location combination.
4. Create a purchase order and add purchased items.
5. Complete the purchase order to receive stock and create lots.
6. Transfer stock between locations when required.
7. Create a sales order and add sold items.
8. Complete the sales order to allocate lots and remove stock.
9. Use alerts, pending pages, history, transactions, transfer records, and audit records to monitor the system.
10. Export required tables to Excel for reporting or further analysis.

## Related Files

- [`README.md`](./README.md)
- [`app.py`](./app.py)
- [`backend.py`](./backend.py)
- [`database.sql`](./database.sql)
