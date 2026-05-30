from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import database as db
import os
from functools import wraps
from fpdf import FPDF
import tempfile
import boto3

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
        if S3_BUCKET and (filename.startswith('avatar_') or filename.startswith('dash_') or filename.startswith('product_')):
            return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{filename}"
        elif filename.startswith('avatar_') or filename.startswith('dash_') or filename.startswith('product_'):
            return url_for('static', filename='uploads/' + filename)
        else:
            return url_for('static', filename='img/' + filename)
    return dict(get_img_url=get_img_url)


# Inicializar DB y crear/actualizar usuarios por defecto con contraseñas seguras
with app.app_context():
    db.init_db()
    conn = db.get_db_connection()
    c = conn.cursor()
    
    # Administrador (Admin123%)
    hashed_admin_pw = generate_password_hash('Admin123%')
    c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', ('admin', hashed_admin_pw, 'admin'))
    else:
        c.execute('UPDATE users SET password = ? WHERE username = ?', (hashed_admin_pw, 'admin'))
    conn.commit()
    
    # Vendedor (Vendedor123%)
    hashed_seller_pw = generate_password_hash('Vendedor123%')
    c.execute('SELECT * FROM users WHERE username = ?', ('vendedor',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', ('vendedor', hashed_seller_pw, 'seller'))
    else:
        c.execute('UPDATE users SET password = ? WHERE username = ?', (hashed_seller_pw, 'vendedor'))
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

@app.route('/dashboard')
@login_required
def dashboard():
    conn = db.get_db_connection()
    total_products = conn.execute('SELECT COUNT(*) as count FROM products').fetchone()['count']
    low_stock = conn.execute('SELECT COUNT(*) as count FROM products WHERE stock < 10').fetchone()['count']
    total_movements = conn.execute('SELECT COUNT(*) as count FROM movements').fetchone()['count']
    total_clients = conn.execute('SELECT COUNT(*) as count FROM clients').fetchone()['count']
    total_providers = conn.execute('SELECT COUNT(*) as count FROM providers').fetchone()['count']
    conn.close()
    return render_template('dashboard.html', total_products=total_products, low_stock=low_stock, 
                           total_movements=total_movements, total_clients=total_clients, total_providers=total_providers)

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
    name = request.form['name']
    description = request.form['description']
    price = request.form['price']
    provider_id = request.form.get('provider_id') or None
    
    image_filename = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            import time
            image_filename = secure_filename(f"product_{int(time.time())}_{file.filename}")
            save_file_to_storage(file, image_filename)
            
    conn = db.get_db_connection()
    conn.execute('INSERT INTO products (name, description, price, provider_id, image) VALUES (?, ?, ?, ?, ?)',
                 (name, description, price, provider_id, image_filename))
    conn.commit()
    conn.close()
    db.log_audit(session['user_id'], 'Crear', 'Inventario', f'Producto creado: {name}')
    flash('Producto agregado exitosamente.', 'success')
    return redirect(url_for('products'))

@app.route('/products/edit/<int:id>', methods=['POST'])
@login_required
def edit_product(id):
    name = request.form['name']
    description = request.form['description']
    
    image_filename = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            import time
            image_filename = secure_filename(f"product_{int(time.time())}_{file.filename}")
            save_file_to_storage(file, image_filename)
            
    conn = db.get_db_connection()
    if session['role'] == 'admin':
        price = request.form['price']
        provider_id = request.form.get('provider_id') or None
        if image_filename:
            conn.execute('UPDATE products SET name = ?, description = ?, price = ?, provider_id = ?, image = ? WHERE id = ?',
                         (name, description, price, provider_id, image_filename, id))
        else:
            conn.execute('UPDATE products SET name = ?, description = ?, price = ?, provider_id = ? WHERE id = ?',
                         (name, description, price, provider_id, id))
    else:
        if image_filename:
            conn.execute('UPDATE products SET name = ?, description = ?, image = ? WHERE id = ?', (name, description, image_filename, id))
        else:
            conn.execute('UPDATE products SET name = ?, description = ? WHERE id = ?', (name, description, id))
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
