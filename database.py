import sqlite3
import pymysql
import os

DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', '')
DB_NAME = os.environ.get('DB_NAME', 'nayoli')

class DBCursor:
    def __init__(self, db_conn):
        self.db_conn = db_conn
        self.real_cursor = None
        
    def execute(self, query, args=()):
        self.real_cursor = self.db_conn.execute(query, args)
        return self.real_cursor
        
    def fetchone(self):
        return self.real_cursor.fetchone() if self.real_cursor else None
        
    def fetchall(self):
        return self.real_cursor.fetchall() if self.real_cursor else []

class DBConnection:
    def __init__(self):
        self.is_mysql = DB_HOST is not None
        if self.is_mysql:
            self.conn = pymysql.connect(
                host=DB_HOST, 
                user=DB_USER, 
                password=DB_PASS, 
                database=DB_NAME, 
                cursorclass=pymysql.cursors.DictCursor
            )
        else:
            self.conn = sqlite3.connect('nayoli.db')
            self.conn.row_factory = sqlite3.Row

    def cursor(self):
        return DBCursor(self)

    def execute(self, query, args=()):
        if self.is_mysql:
            query = query.replace('?', '%s')
            query = query.replace('AUTOINCREMENT', 'AUTO_INCREMENT')
            c = self.conn.cursor()
            c.execute(query, args)
            return c
        else:
            return self.conn.execute(query, args)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db_connection():
    return DBConnection()

def init_db():
    conn = get_db_connection()
    
    # Si es MySQL y queremos soporte inicial rápido, algunas sintaxis de sqlite difieren
    # Por suerte hemos tratado de mantener un SQL bastante estándar.
    
    # Usuarios
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            avatar TEXT,
            theme TEXT DEFAULT 'dark',
            dashboard_image TEXT DEFAULT 'sales_dashboard.png'
        )
    ''')
    
    # Settings (Configuración Global del Negocio)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            logo TEXT,
            currency TEXT DEFAULT '$',
            ticket_message TEXT
        )
    ''')
    
    # Settings (Configuración Global del Negocio)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            logo TEXT,
            currency TEXT DEFAULT '$',
            ticket_message TEXT
        )
    ''')

    # Proveedores
    conn.execute('''
        CREATE TABLE IF NOT EXISTS providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            phone TEXT
        )
    ''')

    # Clientes
    conn.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            client_type TEXT,
            phone TEXT,
            observation TEXT
        )
    ''')

    # Productos
    conn.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            pack_price REAL DEFAULT 0,
            units_per_pack INTEGER DEFAULT 0,
            stock INTEGER NOT NULL,
            category TEXT NOT NULL,
            image TEXT,
            barcode TEXT,
            provider_id INTEGER,
            FOREIGN KEY (provider_id) REFERENCES providers (id)
        )
    ''')

    # Movimientos
    conn.execute('''
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            product_id INTEGER,
            user_id INTEGER,
            client_id INTEGER,
            observation TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    ''')

    # Turnos de Caja (Control de Efectivo)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cash_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            opening_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closing_time TIMESTAMP NULL,
            opening_balance REAL DEFAULT 0,
            closing_balance REAL NULL,
            total_sales REAL DEFAULT 0,
            status TEXT DEFAULT 'open',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Ventas (POS)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_id INTEGER NULL,
            shift_id INTEGER,
            total REAL DEFAULT 0,
            cash_received REAL DEFAULT 0,
            change_given REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'efectivo',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (client_id) REFERENCES clients (id),
            FOREIGN KEY (shift_id) REFERENCES cash_shifts (id)
        )
    ''')

    # Detalle de Ventas
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER,
            product_id INTEGER,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES sales (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')

    # Auditoria
    conn.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            module TEXT NOT NULL,
            description TEXT,
            user_id INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()

    # Asegurar un registro en settings si está vacío
    c = conn.execute('SELECT COUNT(*) as count FROM settings')
    if c.fetchone()['count'] == 0:
        conn.execute("INSERT INTO settings (company_name, logo, currency, ticket_message) VALUES ('Mi Empresa', 'sales_dashboard.png', '$', '¡Gracias por su compra!')")
    
    conn.commit()
    conn.close()

def log_audit(user_id, action, module, description):
    conn = get_db_connection()
    conn.execute('INSERT INTO audit_logs (action, module, description, user_id) VALUES (?, ?, ?, ?)',
              (action, module, description, user_id))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
