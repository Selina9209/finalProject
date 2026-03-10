import sqlite3
from datetime import datetime

# --- DATABASE INITIALIZATION ---

def init_db():
    connection = sqlite3.connect('database.db')
    # Enable foreign keys immediately
    connection.execute("PRAGMA foreign_keys = ON;")

    connection.executescript("""
        DROP TABLE IF EXISTS goals;
        DROP TABLE IF EXISTS expense_records;
        DROP TABLE IF EXISTS expense_items;
        DROP TABLE IF EXISTS categories;

        CREATE TABLE categories (
            category_id INTEGER PRIMARY KEY, 
            name TEXT UNIQUE NOT NULL
        );
        
        CREATE TABLE expense_items (
            item_id INTEGER PRIMARY KEY,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('Fixed', 'Unfixed')),
            default_amount REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        );

        CREATE TABLE expense_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            FOREIGN KEY (item_id) REFERENCES expense_items(item_id)
        );

        CREATE TABLE goals (
            category_id INTEGER PRIMARY KEY,
            monthly_limit REAL DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        );
    """)

    # 1. Insert Categories
    cats = [(1,'housing'), (2,'utilities'), (3,'transportation'), (4,'food'), 
            (5,'children'), (6,'health'), (7,'personal_care'), (8,'entertainment'), (9,'discretionary_cash')]
    connection.executemany("INSERT INTO categories VALUES (?, ?)", cats)

    # 2. Insert Expense Items (The "Fixed" Templates)
    items = [
        (100, 1, 'Mortgage', 'Fixed', 5470), (101, 1, 'Property Tax', 'Fixed', 667),
        (102, 1, 'Insurance', 'Fixed', 138.24), (103, 1, 'Alarm System', 'Fixed', 30),
        (200, 1, 'House Maintenance', 'Unfixed', 0), (104, 2, 'Internet', 'Fixed', 74.58),
        (105, 2, 'Mobile', 'Fixed', 117.29), (106, 2, 'Water', 'Fixed', 69.02),
        (201, 2, 'Electricity', 'Unfixed', 0), (202, 2, 'Heating', 'Unfixed', 0),
        (107, 3, 'Auto Loan', 'Fixed', 1645), (108, 3, 'Auto Insurance', 'Fixed', 381),
        (203, 3, 'Fuel', 'Unfixed', 0), (204, 3, 'Maintenance', 'Unfixed', 0),
        (205, 4, 'Groceries', 'Unfixed', 0), (206, 4, 'Take out', 'Unfixed', 0),
        (109, 5, 'Activities tuition', 'Fixed', 190), (207, 5, 'Daycare', 'Unfixed', 0),
        (208, 5, 'Camps', 'Unfixed', 0), (110, 6, 'Health Insurance', 'Fixed', 573.55),
        (209, 6, 'Dental', 'Unfixed', 0), (210, 6, 'Medical', 'Unfixed', 0),
        (211, 6, 'Wellness', 'Unfixed', 0), (212, 7, 'Clothing', 'Unfixed', 0),
        (215, 7, 'Memberships', 'Unfixed', 0), (213, 8, 'Travel', 'Unfixed', 0),
        (216, 8, 'Gift', 'Unfixed', 0), (214, 9, 'Discretionary Cash', 'Unfixed', 0)
    ]
    connection.executemany("INSERT INTO expense_items VALUES (?, ?, ?, ?, ?)", items)

    # 3. Logic: Week 1 vs The Rest (Current Date Check)
    day_of_month = datetime.now().day
    
    if 1 <= day_of_month <= 7:
        # WEEK 1: Fill records with the Fixed/Default values
        connection.execute("""
            INSERT INTO expense_records (item_id, amount) 
            SELECT item_id, default_amount FROM expense_items
        """)
    else:
        # WEEK 2-4: Start everything at 0 for the Home/Graph views
        connection.execute("""
            INSERT INTO expense_records (item_id, amount) 
            SELECT item_id, 0 FROM expense_items
        """)

    # 4. Initialize goals at 0
    connection.executemany("INSERT INTO goals VALUES (?, 0)", [(i,) for i in range(1, 10)])

    connection.commit()
    connection.close()
    print(f"DB Initialized. Current Day: {day_of_month}. Status: {'Fixed values set' if day_of_month <= 7 else 'Reset to 0'}.")


# --- APP LOGIC FUNCTIONS ---

def get_home_graph_data():
    """Returns data for the dashboard (respects the mid-month 0 reset)."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Sums up records for the current month
    cursor.execute("""
        SELECT i.name, SUM(r.amount) as total 
        FROM expense_items i
        JOIN expense_records r ON i.item_id = r.item_id
        WHERE r.date >= date('now', 'start of month')
        GROUP BY i.item_id
    """)
    data = cursor.fetchall()
    conn.close()
    return data


if __name__ == "__main__":
    init_db()