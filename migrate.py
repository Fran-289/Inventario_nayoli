import sqlite3
import os

DB_PATH = 'nayoli.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        c.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'dark'")
    except sqlite3.OperationalError:
        pass # Column already exists
        
    try:
        c.execute("ALTER TABLE users ADD COLUMN dashboard_image TEXT DEFAULT 'sales_dashboard.png'")
    except sqlite3.OperationalError:
        pass # Column already exists

    conn.commit()
    conn.close()
    print("Migration done.")

if __name__ == '__main__':
    migrate()
