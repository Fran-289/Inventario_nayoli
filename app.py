from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import database as db
import os
from functools import wraps
from fpdf import FPDF
import tempfile
import boto3
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'nayoli_super_secret_key'

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configuración AWS S3
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_REGION = os.environ.get('S3_REGION', 'us-east-1')

def save_file_to_storage(file, filename):
    if S3_BUCKET:
        s3 = boto3.client('s3', region_name=S3_REGION)
        s3.upload_fileobj(file, S3_BUCKET, filename, ExtraArgs={'ACL': 'public-read'})
    else:
        file.save(os.path.join(UPLOAD_FOLDER, filename))

@app.context_processor
def utility_processor():
    def get_img_url(filename):
        if not filename:
            return ''
        if S3_BUCKET and (filename.startswith('avatar_') or filename.startswith('dash_') or filename.startswith('logo_')):
            return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{filename}"
        elif filename.startswith('avatar_') or filename.startswith('dash_') or filename.startswith('logo_'):
            return url_for('static', filename='uploads/' + filename)
        else:
            return url_for('static', filename='img/' + filename)
            
    conn = db.get_db_connection()
    try:
        global_settings = conn.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1').fetchone()
    except Exception:
        global_settings = None
    finally:
        conn.close()
        
    return dict(get_img_url=get_img_url, global_settings=global_settings)



# Inicializar DB y crear usuarios por defecto
with app.app_context():
    db.init_db()
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not c.fetchone():
        hashed_pw = generate_password_hash('admin123')
        c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', ('admin', hashed_pw, 'admin'))
        conn.commit()
    
    c.execute('SELECT * FROM users WHERE username = ?', ('vendedor',))
    if not c.fetchone():
        hashed_pw = generate_password_hash('vendedor123')
        c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', ('vendedor', hashed_pw, 'seller'))
        conn.commit()
    conn.close()

# --- Decoradores ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Acceso denegado. Requiere permisos de Administrador.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Rutas Base ---
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = db.get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['avatar'] = user['avatar']
            
            # Fetch theme and dashboard image if columns exist, otherwise defaults
            # (handled natively by dict if columns were fetched, but we'll use .get in case)
            try:
                session['theme'] = user['theme'] or 'dark'
            except KeyError:
                session['theme'] = 'dark'
                
            try:
                session['dashboard_image'] = user['dashboard_image'] or 'sales_dashboard.png'
            except KeyError:
                session['dashboard_image'] = 'sales_dashboard.png'
                
            db.log_audit(user['id'], 'Login', 'Autenticación', f'Usuario {username} inició sesión.')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        db.log_audit(session['user_id'], 'Logout', 'Autenticación', f'Usuario {session["username"]} cerró sesión.')
    session.clear()
    return redirect(url_for('login'))

@app.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['avatar']
    if file.filename == '':
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('dashboard'))
    
    if file:
        filename = secure_filename(f"avatar_{session['user_id']}_{file.filename}")
        save_file_to_storage(file, filename)
        
        conn = db.get_db_connection()
        conn.execute('UPDATE users SET avatar = ? WHERE id = ?', (filename, session['user_id']))
        conn.commit()
        conn.close()
        
        session['avatar'] = filename
        flash('Foto de perfil actualizada exitosamente.', 'success')
        
    return redirect(url_for('dashboard'))

@app.route('/toggle_theme')
@login_required
def toggle_theme():
    new_theme = 'light' if session.get('theme') == 'dark' else 'dark'
    conn = db.get_db_connection()
    try:
        conn.execute('UPDATE users SET theme = ? WHERE id = ?', (new_theme, session['user_id']))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    session['theme'] = new_theme
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/upload_dashboard_image', methods=['POST'])
@login_required
def upload_dashboard_image():
    if 'dashboard_img' not in request.files:
        flash('No se seleccionó ninguna imagen.', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['dashboard_img']
    if file.filename == '':
        flash('No se seleccionó ninguna imagen.', 'danger')
        return redirect(url_for('dashboard'))
    
    if file:
        filename = secure_filename(f"dash_{session['user_id']}_{file.filename}")
        save_file_to_storage(file, filename)
        
        conn = db.get_db_connection()
        try:
            conn.execute('UPDATE users SET dashboard_image = ? WHERE id = ?', (filename, session['user_id']))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
        
        session['dashboard_image'] = filename
        flash('Imagen del dashboard actualizada.', 'success')
        
    return redirect(url_for('dashboard'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    conn = db.get_db_connection()
    if request.method == 'POST':
        company_name = request.form['company_name']
        currency = request.form['currency']
        ticket_message = request.form['ticket_message']
        
        logo = None
        if 'logo' in request.files and request.files['logo'].filename != '':
            file = request.files['logo']
            filename = secure_filename(f"logo_{file.filename}")
            save_file_to_storage(file, filename)
            logo = filename
            
        if logo:
            conn.execute('UPDATE settings SET company_name = ?, currency = ?, ticket_message = ?, logo = ?',
                         (company_name, currency, ticket_message, logo))
        else:
            conn.execute('UPDATE settings SET company_name = ?, currency = ?, ticket_message = ?',
                         (company_name, currency, ticket_message))
        conn.commit()
        db.log_audit(session['user_id'], 'Editar', 'Configuración', 'Actualizó los ajustes del negocio')
        flash('Configuración guardada exitosamente.', 'success')
        return redirect(request.referrer or url_for('dashboard'))
        
    current_settings = conn.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return render_template('settings.html', settings=current_settings)

@app.route('/dashboard')
@login_required
def dashboard():
    conn = db.get_db_connection()
    total_products = conn.execute('SELECT COUNT(*) as c FROM products').fetchone()['c']
    low_stock = conn.execute('SELECT COUNT(*) as c FROM products WHERE stock < 10').fetchone()['c']
    total_movements = conn.execute('SELECT COUNT(*) as c FROM movements').fetchone()['c']
    total_clients = conn.execute('SELECT COUNT(*) as c FROM clients').fetchone()['c']
    total_providers = conn.execute('SELECT COUNT(*) as c FROM providers').fetchone()['c']
    
    # Check shift
    current_shift = conn.execute('SELECT * FROM cash_shifts WHERE user_id = ? AND status = "open"', (session['user_id'],)).fetchone()
    
    conn.close()
    return render_template('dashboard.html', 
                           total_products=total_products, 
                           low_stock=low_stock,
                           total_movements=total_movements,
                           total_clients=total_clients,
                           total_providers=total_providers,
                           current_shift=current_shift)

@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    conn = db.get_db_connection()
    # Ventas de los ultimos 7 dias
    sales = conn.execute('''
        SELECT date(date) as d, SUM(total) as t 
        FROM sales 
        WHERE date(date) >= date('now', '-7 days')
        GROUP BY date(date)
        ORDER BY d ASC
    ''').fetchall()
    
    # Top 5 productos mas vendidos
    top_products = conn.execute('''
        SELECT p.name, SUM(si.quantity) as q
        FROM sale_items si
        JOIN products p ON si.product_id = p.id
        GROUP BY p.id
        ORDER BY q DESC
        LIMIT 5
    ''').fetchall()
    conn.close()
    
    return json.dumps({
        'sales_dates': [s['d'] for s in sales],
        'sales_totals': [s['t'] for s in sales],
        'top_names': [p['name'] for p in top_products],
        'top_qty': [p['q'] for p in top_products]
    })

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

@app.route('/api/reports/data')
@login_required
def api_reports_data():
    period = request.args.get('period', 'day') # shift, day, month, year
    conn = db.get_db_connection()
    
    if period == 'shift':
        # ultimos 15 turnos
        data = conn.execute('''
            SELECT c.id as label, c.total_sales as total, c.opening_time, c.closing_time, u.username
            FROM cash_shifts c
            LEFT JOIN users u ON c.user_id = u.id
            ORDER BY c.opening_time DESC LIMIT 15
        ''').fetchall()
        labels = [f"Turno #{d['label']}" for d in reversed(data)]
        totals = [d['total'] for d in reversed(data)]
        records = [{
            'col1': f"Turno #{d['label']} ({d['username']})",
            'col2': d['opening_time'],
            'col3': d['closing_time'] if d['closing_time'] else 'En curso',
            'total': d['total']
        } for d in data]
        
    elif period == 'month':
        # ultimos 12 meses
        data = conn.execute('''
            SELECT strftime('%Y-%m', date) as label, SUM(total) as total
            FROM sales
            GROUP BY label
            ORDER BY label DESC LIMIT 12
        ''').fetchall()
        labels = [d['label'] for d in reversed(data)]
        totals = [d['total'] for d in reversed(data)]
        records = [{'col1': d['label'], 'col2': '-', 'col3': '-', 'total': d['total']} for d in data]
        
    elif period == 'year':
        # ultimos 5 años
        data = conn.execute('''
            SELECT strftime('%Y', date) as label, SUM(total) as total
            FROM sales
            GROUP BY label
            ORDER BY label DESC LIMIT 5
        ''').fetchall()
        labels = [d['label'] for d in reversed(data)]
        totals = [d['total'] for d in reversed(data)]
        records = [{'col1': d['label'], 'col2': '-', 'col3': '-', 'total': d['total']} for d in data]
        
    else: # day
        # ultimos 30 dias
        data = conn.execute('''
            SELECT date(date) as label, SUM(total) as total
            FROM sales
            WHERE date(date) >= date('now', '-30 days')
            GROUP BY label
            ORDER BY label DESC
        ''').fetchall()
        labels = [d['label'] for d in reversed(data)]
        totals = [d['total'] for d in reversed(data)]
        records = [{'col1': d['label'], 'col2': '-', 'col3': '-', 'total': d['total']} for d in data]
        
    conn.close()
    return json.dumps({
        'labels': labels,
        'totals': totals,
        'records': records
    })

# --- Módulo Productos ---
@app.route('/products')
@login_required
def products():
    conn = db.get_db_connection()
    prods = conn.execute('SELECT p.*, pr.name as provider_name FROM products p LEFT JOIN providers pr ON p.provider_id = pr.id').fetchall()
    providers = conn.execute('SELECT * FROM providers').fetchall()
    conn.close()
    return render_template('products.html', products=prods, providers=providers)

@app.route('/products/add', methods=['POST'])
@login_required
@admin_required
def add_product():
    barcode = request.form.get('barcode', '')
    name = request.form['name']
    description = request.form['description']
    price = request.form['price']
    pack_price = float(request.form.get('pack_price') or 0)
    units_per_pack = int(request.form.get('units_per_pack') or 0)
    provider_id = request.form.get('provider_id') or None
    
    conn = db.get_db_connection()
    conn.execute('INSERT INTO products (barcode, name, description, price, pack_price, units_per_pack, provider_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
                 (barcode, name, description, price, pack_price, units_per_pack, provider_id))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Crear', 'Inventario', f'Producto creado: {name}')
    flash('Producto agregado exitosamente.', 'success')
    return redirect(url_for('products'))

@app.route('/products/edit/<int:id>', methods=['POST'])
@login_required
def edit_product(id):
    barcode = request.form.get('barcode', '')
    name = request.form['name']
    description = request.form['description']
    conn = db.get_db_connection()
    if session['role'] == 'admin':
        price = request.form['price']
        pack_price = float(request.form.get('pack_price') or 0)
        units_per_pack = int(request.form.get('units_per_pack') or 0)
        provider_id = request.form.get('provider_id') or None
        conn.execute('UPDATE products SET barcode = ?, name = ?, description = ?, price = ?, pack_price = ?, units_per_pack = ?, provider_id = ? WHERE id = ?',
                     (barcode, name, description, price, pack_price, units_per_pack, provider_id, id))
    else:
        conn.execute('UPDATE products SET barcode = ?, name = ?, description = ? WHERE id = ?', (barcode, name, description, id))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Editar', 'Inventario', f'Producto editado ID: {id}')
    flash('Producto actualizado.', 'success')
    return redirect(url_for('products'))

@app.route('/products/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_product(id):
    conn = db.get_db_connection()
    prod = conn.execute('SELECT name FROM products WHERE id = ?', (id,)).fetchone()
    conn.execute('DELETE FROM products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Eliminar', 'Inventario', f'Producto eliminado: {prod["name"]}')
    flash('Producto eliminado.', 'success')
    return redirect(url_for('products'))

# --- Módulo Movimientos ---
@app.route('/movements')
@login_required
def movements():
    conn = db.get_db_connection()
    movs = conn.execute('''
        SELECT m.*, p.name as product_name, u.username, c.name as client_name
        FROM movements m 
        JOIN products p ON m.product_id = p.id 
        JOIN users u ON m.user_id = u.id 
        LEFT JOIN clients c ON m.client_id = c.id
        ORDER BY m.date DESC
    ''').fetchall()
    prods = conn.execute('SELECT * FROM products').fetchall()
    clients = conn.execute('SELECT * FROM clients').fetchall()
    conn.close()
    return render_template('movements.html', movements=movs, products=prods, clients=clients)

@app.route('/movements/add', methods=['POST'])
@login_required
def add_movement():
    type = request.form['type']
    quantity = int(request.form['quantity'])
    product_id = int(request.form['product_id'])
    
    # Solo aplicable si es salida (venta)
    client_id = request.form.get('client_id')
    observation = request.form.get('observation', '')
    
    if type == 'in':
        client_id = None
        observation = ''
        
    conn = db.get_db_connection()
    prod = conn.execute('SELECT stock, name FROM products WHERE id = ?', (product_id,)).fetchone()
    
    if type == 'out' and prod['stock'] < quantity:
        flash('Stock insuficiente para la salida.', 'danger')
        conn.close()
        return redirect(url_for('movements'))
        
    conn.execute('INSERT INTO movements (type, quantity, product_id, user_id, client_id, observation) VALUES (?, ?, ?, ?, ?, ?)',
                 (type, quantity, product_id, session['user_id'], client_id, observation))
    
    new_stock = prod['stock'] + quantity if type == 'in' else prod['stock'] - quantity
    conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product_id))
    
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Registrar', 'Movimientos', f'Movimiento {type} de {quantity} unidades para {prod["name"]}')
    flash('Movimiento registrado exitosamente.', 'success')
    return redirect(url_for('movements'))

@app.route('/movements/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_movement(id):
    conn = db.get_db_connection()
    mov = conn.execute('SELECT * FROM movements WHERE id = ?', (id,)).fetchone()
    prod = conn.execute('SELECT stock, name FROM products WHERE id = ?', (mov['product_id'],)).fetchone()
    
    new_stock = prod['stock'] - mov['quantity'] if mov['type'] == 'in' else prod['stock'] + mov['quantity']
    conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, mov['product_id']))
    conn.execute('DELETE FROM movements WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Eliminar', 'Movimientos', f'Movimiento ID {id} eliminado. Stock revertido.')
    flash('Movimiento eliminado y stock revertido.', 'success')
    return redirect(url_for('movements'))

# --- Módulo Proveedores ---
@app.route('/providers')
@login_required
def providers():
    conn = db.get_db_connection()
    provs = conn.execute('SELECT * FROM providers').fetchall()
    conn.close()
    return render_template('providers.html', providers=provs)

@app.route('/providers/add', methods=['POST'])
@login_required
@admin_required
def add_provider():
    name = request.form['name']
    contact = request.form['contact']
    phone = request.form['phone']
    conn = db.get_db_connection()
    conn.execute('INSERT INTO providers (name, contact, phone) VALUES (?, ?, ?)', (name, contact, phone))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Crear', 'Proveedores', f'Proveedor creado: {name}')
    flash('Proveedor agregado.', 'success')
    return redirect(url_for('providers'))

# --- Módulo Clientes ---
@app.route('/clients')
@login_required
def clients():
    conn = db.get_db_connection()
    clis = conn.execute('SELECT * FROM clients').fetchall()
    conn.close()
    return render_template('clients.html', clients=clis)

@app.route('/clients/add', methods=['POST'])
@login_required
def add_client():
    name = request.form['name']
    client_type = request.form['client_type']
    phone = request.form['phone']
    observation = request.form.get('observation', '')
    
    conn = db.get_db_connection()
    conn.execute('INSERT INTO clients (name, client_type, phone, observation) VALUES (?, ?, ?, ?)', (name, client_type, phone, observation))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Crear', 'Clientes', f'Cliente creado: {name}')
    flash('Cliente agregado exitosamente.', 'success')
    return redirect(url_for('clients'))

# --- Punto de Venta (POS) y Caja ---
@app.route('/pos')
@login_required
def pos():
    conn = db.get_db_connection()
    # Check if there is an open shift for this user
    shift = conn.execute('SELECT * FROM cash_shifts WHERE user_id = ? AND status = "open"', (session['user_id'],)).fetchone()
    
    if not shift:
        conn.close()
        return render_template('pos_open_shift.html')
        
    clients = conn.execute('SELECT * FROM clients').fetchall()
    conn.close()
    return render_template('pos.html', shift=shift, clients=clients)

@app.route('/pos/open_shift', methods=['POST'])
@login_required
def open_shift():
    opening_balance = float(request.form.get('opening_balance', 0))
    conn = db.get_db_connection()
    conn.execute('INSERT INTO cash_shifts (user_id, opening_balance) VALUES (?, ?)', (session['user_id'], opening_balance))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Abrir Caja', 'POS', f'Caja abierta con ${opening_balance}')
    flash('Turno de caja abierto exitosamente.', 'success')
    return redirect(url_for('pos'))

@app.route('/pos/close_shift', methods=['POST'])
@login_required
def close_shift():
    closing_balance = float(request.form.get('closing_balance', 0))
    conn = db.get_db_connection()
    shift = conn.execute('SELECT * FROM cash_shifts WHERE user_id = ? AND status = "open"', (session['user_id'],)).fetchone()
    
    if shift:
        conn.execute('UPDATE cash_shifts SET closing_balance = ?, closing_time = CURRENT_TIMESTAMP, status = "closed" WHERE id = ?', 
                     (closing_balance, shift['id']))
        conn.commit()
        db.log_audit(session['user_id'], 'Cerrar Caja', 'POS', f'Caja cerrada. Total Ventas: ${shift["total_sales"]}')
        flash('Turno cerrado exitosamente.', 'success')
        
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/api/pos/search')
@login_required
def pos_search():
    query = request.args.get('q', '')
    conn = db.get_db_connection()
    # Search by barcode or name
    products = conn.execute('SELECT id, barcode, name, price, stock, pack_price, units_per_pack FROM products WHERE (barcode = ? OR name LIKE ?) AND stock > 0', 
                            (query, f'%{query}%')).fetchall()
    conn.close()
    return json.dumps([dict(p) for p in products])

@app.route('/pos/checkout', methods=['POST'])
@login_required
def checkout():
    conn = db.get_db_connection()
    shift = conn.execute('SELECT * FROM cash_shifts WHERE user_id = ? AND status = "open"', (session['user_id'],)).fetchone()
    if not shift:
        conn.close()
        return redirect(url_for('pos'))
        
    client_id = request.form.get('client_id') or None
    cash_received = float(request.form.get('cash_received', 0))
    payment_method = request.form.get('payment_method', 'efectivo')
    cart_data = json.loads(request.form.get('cart', '[]'))
    
    if not cart_data:
        flash('El carrito está vacío.', 'danger')
        conn.close()
        return redirect(url_for('pos'))
        
    total = 0
    for item in cart_data:
        is_pack = item.get('is_pack', False)
        units_per_pack = item.get('units_per_pack') or 0
        pack_price = item.get('pack_price') or 0
        if not is_pack and units_per_pack > 0 and pack_price > 0:
            packs = item['qty'] // units_per_pack
            remainder = item['qty'] % units_per_pack
            total += (packs * pack_price) + (remainder * item['price'])
        else:
            total += item['price'] * item['qty']
            
    change_given = cash_received - total if cash_received >= total else 0
    if payment_method == 'mixto':
        change_given = 0 # No hay cambio en mixto, el efectivo se cobra exacto y el resto en tarjeta
    
    # Register Sale
    c = conn.execute('INSERT INTO sales (user_id, client_id, shift_id, total, cash_received, change_given, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?)',
                 (session['user_id'], client_id, shift['id'], total, cash_received, change_given, payment_method))
    
    sale_id = c.lastrowid or c.db_conn.execute('SELECT last_insert_rowid()').fetchone()[0] if not getattr(c, 'lastrowid', None) else c.lastrowid
    if not sale_id: # fallback sqlite
        sale_id = conn.execute('SELECT seq FROM sqlite_sequence WHERE name="sales"').fetchone()[0]

    # Process items
    for item in cart_data:
        is_pack = item.get('is_pack', False)
        units_per_pack = item.get('units_per_pack') or 0
        pack_price = item.get('pack_price') or 0
        
        # Calculate subtotal with auto-wholesale logic
        if not is_pack and units_per_pack > 0 and pack_price > 0:
            packs = item['qty'] // units_per_pack
            remainder = item['qty'] % units_per_pack
            subtotal = (packs * pack_price) + (remainder * item['price'])
        else:
            subtotal = item['price'] * item['qty']
            
        real_qty = item['qty'] * units_per_pack if is_pack and units_per_pack > 0 else item['qty']
        obs = f'Venta POS #{sale_id} (Fardo)' if is_pack else f'Venta POS #{sale_id}'
        
        # Guardamos el unit_price que pagaron en promedio o el original
        conn.execute('INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, subtotal) VALUES (?, ?, ?, ?, ?)',
                     (sale_id, item['id'], item['qty'], item['price'], subtotal))
        # Reduce Stock
        conn.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (real_qty, item['id']))
        # Movement record
        conn.execute('INSERT INTO movements (type, quantity, product_id, user_id, client_id, observation) VALUES (?, ?, ?, ?, ?, ?)',
                     ('out', real_qty, item['id'], session['user_id'], client_id, obs))
                     
    # Update shift total
    conn.execute('UPDATE cash_shifts SET total_sales = total_sales + ? WHERE id = ?', (total, shift['id']))
    
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Vender', 'POS', f'Venta POS #{sale_id} por ${total}')
    flash('Venta completada exitosamente.', 'success')
    return redirect(url_for('pos_ticket', id=sale_id))

@app.route('/pos/ticket/<int:id>')
@login_required
def pos_ticket(id):
    conn = db.get_db_connection()
    sale = conn.execute('SELECT s.*, u.username, c.name as client_name FROM sales s LEFT JOIN users u ON s.user_id = u.id LEFT JOIN clients c ON s.client_id = c.id WHERE s.id = ?', (id,)).fetchone()
    items = conn.execute('SELECT si.*, p.name FROM sale_items si JOIN products p ON si.product_id = p.id WHERE si.sale_id = ?', (id,)).fetchall()
    settings = conn.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return render_template('ticket.html', sale=sale, items=items, settings=settings)

@app.route('/pos/ticket/<int:id>/pdf')
@login_required
def pos_ticket_pdf(id):
    conn = db.get_db_connection()
    sale = conn.execute('SELECT s.*, u.username, c.name as client_name FROM sales s LEFT JOIN users u ON s.user_id = u.id LEFT JOIN clients c ON s.client_id = c.id WHERE s.id = ?', (id,)).fetchone()
    items = conn.execute('SELECT si.*, p.name FROM sale_items si JOIN products p ON si.product_id = p.id WHERE si.sale_id = ?', (id,)).fetchall()
    settings = conn.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    
    if not sale:
        flash('Ticket no encontrado.', 'danger')
        return redirect(url_for('pos'))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    company_name = settings['company_name'] if settings and settings['company_name'] else 'Nayoli'
    pdf.set_font("Arial", style="B", size=16)
    pdf.cell(200, 10, txt=company_name, ln=1, align="C")
    
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 6, txt=f"Ticket de Venta #{sale['id']}", ln=1, align="C")
    pdf.cell(200, 6, txt=f"Fecha: {sale['date']}", ln=1, align="C")
    pdf.cell(200, 6, txt=f"Cajero: {sale['username']}", ln=1, align="C")
    
    pdf.ln(5)
    pdf.set_font("Arial", style="B", size=10)
    pdf.cell(30, 8, txt="Cant", border=1)
    pdf.cell(120, 8, txt="Descripcion", border=1)
    pdf.cell(40, 8, txt="Importe", border=1, ln=1, align="R")
    
    pdf.set_font("Arial", size=10)
    for item in items:
        # Avoid char mapping issues
        name_str = item['name'].encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(30, 8, txt=str(item['quantity']), border=1)
        pdf.cell(120, 8, txt=name_str, border=1)
        pdf.cell(40, 8, txt=f"${item['subtotal']:.2f}", border=1, ln=1, align="R")
        
    pdf.ln(5)
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(150, 8, txt="Total a Pagar:", align="R")
    pdf.cell(40, 8, txt=f"${sale['total']:.2f}", ln=1, align="R")
    
    pdf.set_font("Arial", size=10)
    pdf.cell(150, 6, txt="Efectivo Recibido:", align="R")
    pdf.cell(40, 6, txt=f"${sale['cash_received']:.2f}", ln=1, align="R")
    pdf.cell(150, 6, txt="Cambio:", align="R")
    pdf.cell(40, 6, txt=f"${sale['change_given']:.2f}", ln=1, align="R")
    
    pdf.ln(10)
    msg = settings['ticket_message'] if settings and settings['ticket_message'] else 'Gracias por su compra!'
    msg = msg.encode('latin-1', 'replace').decode('latin-1')
    pdf.cell(200, 6, txt=msg, ln=1, align="C")
    pdf.cell(200, 6, txt="*** Este documento no tiene validez fiscal ***", ln=1, align="C")
    
    temp_dir = tempfile.gettempdir()
    pdf_path = os.path.join(temp_dir, f'ticket_{id}.pdf')
    pdf.output(pdf_path)
    
    return send_file(pdf_path, as_attachment=True, download_name=f'Ticket_Venta_{id}.pdf')

# --- Módulo Auditoría ---
@app.route('/audit')
@login_required
@admin_required
def audit():
    conn = db.get_db_connection()
    logs = conn.execute('''
        SELECT a.*, u.username 
        FROM audit_logs a 
        LEFT JOIN users u ON a.user_id = u.id 
        ORDER BY a.date DESC
    ''').fetchall()
    conn.close()
    return render_template('audit.html', logs=logs)

# --- PDFs ---
@app.route('/pdf/<module>')
@login_required
def generate_pdf(module):
    conn = db.get_db_connection()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    if module == 'products':
        pdf.cell(200, 10, txt="Reporte de Inventario (Stock)", ln=True, align='C')
        data = conn.execute('SELECT id, name, stock, price FROM products').fetchall()
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(20, 10, "ID", 1)
        pdf.cell(80, 10, "Nombre", 1)
        pdf.cell(30, 10, "Stock", 1)
        pdf.cell(40, 10, "Precio", 1)
        pdf.ln()
        pdf.set_font("Arial", '', 10)
        for row in data:
            pdf.cell(20, 10, str(row['id']), 1)
            pdf.cell(80, 10, row['name'], 1)
            pdf.cell(30, 10, str(row['stock']), 1)
            pdf.cell(40, 10, f"${row['price']:.2f}", 1)
            pdf.ln()
            
    elif module == 'movements':
        pdf.cell(200, 10, txt="Reporte de Movimientos", ln=True, align='C')
        data = conn.execute('''
            SELECT m.id, m.type, m.quantity, p.name as pname, c.name as cname, m.date 
            FROM movements m 
            JOIN products p ON m.product_id = p.id
            LEFT JOIN clients c ON m.client_id = c.id
        ''').fetchall()
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(15, 10, "ID", 1)
        pdf.cell(20, 10, "Tipo", 1)
        pdf.cell(60, 10, "Producto", 1)
        pdf.cell(15, 10, "Cant.", 1)
        pdf.cell(40, 10, "Cliente", 1)
        pdf.cell(40, 10, "Fecha", 1)
        pdf.ln()
        pdf.set_font("Arial", '', 8)
        for row in data:
            tipo = "Entrada" if row['type'] == 'in' else "Salida"
            pdf.cell(15, 10, str(row['id']), 1)
            pdf.cell(20, 10, tipo, 1)
            pdf.cell(60, 10, row['pname'], 1)
            pdf.cell(15, 10, str(row['quantity']), 1)
            pdf.cell(40, 10, str(row['cname'] or '-'), 1)
            pdf.cell(40, 10, row['date'][:10], 1)
            pdf.ln()
            
    elif module == 'providers':
        pdf.cell(200, 10, txt="Directorio de Proveedores", ln=True, align='C')
        data = conn.execute('SELECT * FROM providers').fetchall()
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(20, 10, "ID", 1)
        pdf.cell(80, 10, "Nombre", 1)
        pdf.cell(50, 10, "Contacto", 1)
        pdf.cell(40, 10, "Telefono", 1)
        pdf.ln()
        pdf.set_font("Arial", '', 10)
        for row in data:
            pdf.cell(20, 10, str(row['id']), 1)
            pdf.cell(80, 10, row['name'], 1)
            pdf.cell(50, 10, str(row['contact'] or ''), 1)
            pdf.cell(40, 10, str(row['phone'] or ''), 1)
            pdf.ln()
            
    elif module == 'clients':
        pdf.cell(200, 10, txt="Directorio de Clientes", ln=True, align='C')
        data = conn.execute('SELECT * FROM clients').fetchall()
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(20, 10, "ID", 1)
        pdf.cell(60, 10, "Nombre", 1)
        pdf.cell(40, 10, "Tipo", 1)
        pdf.cell(30, 10, "Telefono", 1)
        pdf.cell(40, 10, "Observacion", 1)
        pdf.ln()
        pdf.set_font("Arial", '', 10)
        for row in data:
            pdf.cell(20, 10, str(row['id']), 1)
            pdf.cell(60, 10, row['name'], 1)
            pdf.cell(40, 10, str(row['client_type'] or ''), 1)
            pdf.cell(30, 10, str(row['phone'] or ''), 1)
            pdf.cell(40, 10, str(row['observation'] or ''), 1)
            pdf.ln()

    conn.close()
    fd, temp_path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    pdf.output(temp_path)
    db.log_audit(session['user_id'], 'Exportar', module.capitalize(), f'PDF generado para {module}')
    return send_file(temp_path, as_attachment=True, download_name=f'reporte_{module}.pdf')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
