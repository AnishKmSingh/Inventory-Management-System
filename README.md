# Inventory Management System

A desktop inventory and warehouse management application built with Python, Tkinter/ttkbootstrap, and MySQL. The application manages products, suppliers, customers, storage locations, purchase orders, sales orders, stock transfers, inventory history, and audit records through a graphical interface.

## Features

- Username/password authentication
- Automatic default administrator creation on an empty database
- Staff account registration
- Admin-only access to product history, transaction logs, and audit logs
- Product, supplier, and customer management
- Storage location and inventory-by-location management
- Stock transfers between storage locations
- Purchase order processing and stock-in tracking
- Sales order processing and stock-out tracking
- Purchase and sales order notes
- Pending purchase and sales order views
- Low-stock and out-of-stock alerts
- Lot-based inventory tracking and product history
- Stock transaction logging
- Transfer logging between storage locations
- Excel export for supported data tables
- Audit logging for data changes and Excel exports
- Dashboard inventory valuation and sales profitability metrics
- Light and dark display themes
- Logout and session restart
- Transaction rollback and validation for stock-changing operations

## Technology Stack

- Python 3
- Tkinter with `ttkbootstrap`
- MySQL
- `mysql-connector-python`
- `openpyxl`
- SQL schema, foreign keys, and triggers in `database.sql`

## Project Files

- [`app.py`](./app.py) - Desktop GUI, login window, navigation, forms, tables, alerts, and order workflows
- [`backend.py`](./backend.py) - MySQL connection, queries, validations, transactions, stock logic, lot allocation, and logging
- [`database.sql`](./database.sql) - Database tables, relationships, and stock transaction triggers
- [`Operations.md`](./Operations.md) - Detailed list of supported operations and system functionality
- `Research Papers/` - Supporting research and project material

## Requirements

- Python 3.9 or newer
- MySQL Server
- A graphical desktop environment for Tkinter

Install the Python dependencies:

```bash
pip install ttkbootstrap mysql-connector-python openpyxl
```

## Database Setup

1. Start MySQL Server.
2. Create the `Inventory` database.
3. Execute `database.sql` using MySQL Workbench or the MySQL client.

Example:

```sql
CREATE DATABASE Inventory;
USE Inventory;
SOURCE database.sql;
```

The application also checks for order-note columns, stock-transfer tables, and the `EXPORT` audit action when it starts and creates or updates those schema elements if they are missing.

## Database Configuration

Update the `DB_CONFIG` dictionary in [`backend.py`](./backend.py) with the credentials for your local MySQL installation:

```python
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_password",
    "database": "Inventory"
}
```

Do not commit real database credentials to a public repository. Prefer environment variables or a local configuration file for deployment.

## Run the Application

From the project directory, run:

```bash
python app.py
```

The login window opens first. After successful authentication, the main inventory dashboard is displayed.

## Default Administrator Account

If the `users` table is empty, the application creates:

- Username: `admin`
- Password: `admin@123`
- Role: `admin`

Change or replace this development credential before using the application in a real environment.

## Access Roles

- **Admin** - Can use all normal inventory functions and view Product History, Transaction Log, and Audit Log.
- **Staff** - Can use operational inventory, purchasing, sales, and alert screens, but restricted administrator-only history and log pages are hidden and protected.

## User Interface

- The application uses the `pulse` ttkbootstrap theme by default.
- Use the sidebar theme button to switch between light mode and dark mode.
- Use Logout to close the current authenticated session and return to the login window.
- Navigation and data tables are scrollable and support row selection/hover styling.

## Main GUI Pages

- Dashboard
- Products
- Suppliers
- Customers
- Storage Locations
- Items in Storage
- Purchase Orders
- Purchased Items
- Sales Orders
- Sold Items
- Low Stock
- Out of Stock
- Pending Purchases
- Pending Sales
- Product History (admin only)
- Transaction Log and Transfer Log (admin only)
- Audit Log (admin only)

## Dashboard Metrics

In addition to inventory counts and pending-order counts, the dashboard shows:

- Number of storage locations
- Total inventory cost basis
- Total retail value
- Unrealized gross margin and margin percentage
- Completed-order net sales revenue
- Cost of goods sold (COGS)
- Realized gross profit and profit percentage

## Excel Export

Data tables can be exported to `.xlsx` files using the **Export to Excel** action. The export:

- Opens a save dialog with a timestamped filename.
- Writes table headers and all currently displayed rows.
- Creates formatted worksheets with bold headers and automatic column widths.
- Shows a message when there are no rows to export.
- Records the export in the audit log with the user, title, path, and row count.

The transaction page provides separate exports for the transaction log and transfer log. The dashboard itself is not exported.

## Important Behavior

- Completing a purchase order adds stock to the selected inventory location, updates product totals, and creates inventory lots.
- Completing a sales order validates total and location stock, consumes lots in receipt order, updates stock totals, and records product history.
- Cancelling or deleting a completed order reverses its stock movement when the underlying stock can be safely restored.
- Stock transfers preserve lot information and require sufficient completed-source stock.
- Stock transfers are listed in the administrator-only Transfer Log.
- An inventory-by-location row can only be deleted when its stock is zero.
- Database transactions commit successful changes and roll back failed stock-changing operations.

## Documentation

See [`Operations.md`](./Operations.md) for the complete operation-by-operation description of the application.

## License

This project is provided for educational use and does not include a formal license unless otherwise specified.



<img width="1246" height="707" alt="image" src="https://github.com/user-attachments/assets/d935fd74-00cc-4d23-9f0a-fa2d05dadad6" />
