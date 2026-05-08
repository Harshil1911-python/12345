import os, csv, pickle, uuid, hashlib, secrets
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_from_directory)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR  = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

ADMIN_EMAIL    = 'henosis4india@gmail.com'
ADMIN_PASSWORD = hashlib.sha256('Henosis@2024'.encode()).hexdigest()

PRODUCT_FIELDS = ['id','name','price','description','category','stock',
                  'only_one','images','featured','created_at']
ORDER_FIELDS   = ['id','customer_name','email','phone','address','city',
                  'pincode','items','total','status','payment_status','created_at']

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def read_csv(fname):
    path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(path):
        return []
    with open(path, 'r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_csv(fname, rows, fieldnames):
    path = os.path.join(DATA_DIR, fname)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

def save_dat(fname, data):
    with open(os.path.join(DATA_DIR, fname), 'wb') as f:
        pickle.dump(data, f)

def load_settings():
    return {r['key']: r['value'] for r in read_csv('settings.csv')}

def save_settings(s):
    write_csv('settings.csv', [{'key': k, 'value': v} for k, v in s.items()], ['key', 'value'])
    save_dat('settings.dat', s)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def ensure_data_files():
    os.makedirs(DATA_DIR,   exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    schemas = [
        ('products.csv',  PRODUCT_FIELDS),
        ('orders.csv',    ORDER_FIELDS),
        ('settings.csv',  ['key', 'value']),
        ('customers.csv', ['id','name','email','phone','address','created_at']),
    ]
    for fname, hdrs in schemas:
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            with open(path, 'w', newline='') as f:
                csv.writer(f).writerow(hdrs)
    s = load_settings()
    defaults = {
        'tagline':     'Crafted to stand alone.',
        'hero_text':   'Where rarity meets artistry. Each piece tells a story that belongs to one soul.',
        'banner_text': 'Free shipping on orders above \u20b92000 \u00b7 Exclusively crafted \u00b7 One of a kind',
        'logo_text':   'HENOSIS',
        'logo_image':  '',
    }
    changed = False
    for k, v in defaults.items():
        if k not in s:
            s[k] = v
            changed = True
    if changed:
        save_settings(s)

ensure_data_files()

# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def get_products():
    return read_csv('products.csv')

def save_products(p):
    write_csv('products.csv', p, PRODUCT_FIELDS)
    save_dat('products.dat', p)

def get_product(pid):
    return next((p for p in get_products() if p['id'] == pid), None)

def get_orders():
    return read_csv('orders.csv')

def save_orders(o):
    write_csv('orders.csv', o, ORDER_FIELDS)
    save_dat('orders.dat', o)

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    s = load_settings()
    p = get_products()
    return render_template('index.html', settings=s,
                           featured=[x for x in p if x.get('featured') == 'true'][:6],
                           products=p[:8])

@app.route('/shop')
def shop():
    s   = load_settings()
    p   = get_products()
    cat = request.args.get('category', '')
    if cat:
        p = [x for x in p if x.get('category', '').lower() == cat.lower()]
    cats = sorted({x['category'] for x in get_products() if x.get('category')})
    return render_template('shop.html', settings=s, products=p,
                           categories=cats, selected_category=cat)

@app.route('/product/<pid>')
def product_detail(pid):
    s       = load_settings()
    product = get_product(pid)
    if not product:
        return redirect(url_for('shop'))
    related = [p for p in get_products()
               if p['id'] != pid and p.get('category') == product.get('category')][:4]
    return render_template('product.html', settings=s, product=product, related=related)

@app.route('/cart')
def cart():
    return render_template('cart.html', settings=load_settings())

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    s = load_settings()
    if request.method == 'POST':
        data       = request.get_json(silent=True) or {}
        cart_items = data.get('cart', [])
        cust       = data.get('customer', {})
        if not cart_items or not cust.get('name'):
            return jsonify({'success': False, 'error': 'Missing data'}), 400

        products  = get_products()
        total     = 0
        items_str = []
        for ci in cart_items:
            p = next((x for x in products if x['id'] == ci['id']), None)
            if p:
                qty   = int(ci.get('qty', 1))
                price = float(p['price'])
                total += price * qty
                items_str.append(f"{p['name']} x{qty} @\u20b9{price:.0f}")

        order = {
            'id':             str(uuid.uuid4())[:8].upper(),
            'customer_name':  cust.get('name', ''),
            'email':          cust.get('email', ''),
            'phone':          cust.get('phone', ''),
            'address':        cust.get('address', ''),
            'city':           cust.get('city', ''),
            'pincode':        cust.get('pincode', ''),
            'items':          ' | '.join(items_str),
            'total':          f'{total:.2f}',
            'status':         'Pending',
            'payment_status': 'Unpaid',
            'created_at':     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        orders = get_orders()
        orders.append(order)
        save_orders(orders)

        for ci in cart_items:
            for p in products:
                if p['id'] == ci['id']:
                    if p.get('only_one') == 'true':
                        p['stock'] = '0'
                    else:
                        p['stock'] = str(max(0, int(p.get('stock', '0')) - int(ci.get('qty', 1))))
        save_products(products)
        return jsonify({'success': True, 'order_id': order['id']})

    return render_template('checkout.html', settings=s)

@app.route('/order-success')
def order_success():
    return render_template('order_success.html', settings=load_settings(),
                           order_id=request.args.get('id', ''))

@app.route('/about')
def about():
    return render_template('about.html', settings=load_settings())

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route('/api/products')
def api_products():
    return jsonify(get_products())

@app.route('/api/product/<pid>')
def api_product(pid):
    p = get_product(pid)
    return jsonify(p) if p else ('Not found', 404)

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route('/henosis-admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '')
        phash = hashlib.sha256(request.form.get('password', '').encode()).hexdigest()
        if email == ADMIN_EMAIL and phash == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('admin/login.html')

@app.route('/henosis-admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/henosis-admin/dashboard')
@admin_required
def admin_dashboard():
    p = get_products()
    o = get_orders()
    s = load_settings()
    stats = {
        'products': len(p),
        'orders':   len(o),
        'revenue':  sum(float(x.get('total', 0)) for x in o),
        'pending':  sum(1 for x in o if x.get('status') == 'Pending'),
    }
    recent = sorted(o, key=lambda x: x.get('created_at', ''), reverse=True)[:10]
    return render_template('admin/dashboard.html', settings=s, stats=stats,
                           recent_orders=recent, products=p)

@app.route('/henosis-admin/products')
@admin_required
def admin_products():
    return render_template('admin/products.html', settings=load_settings(),
                           products=get_products())

@app.route('/henosis-admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    s = load_settings()
    if request.method == 'POST':
        images = []
        for f in request.files.getlist('images'):
            if f and f.filename and allowed_file(f.filename):
                fn = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
                f.save(os.path.join(UPLOAD_DIR, fn))
                images.append(fn)
        product = {
            'id':          str(uuid.uuid4())[:8].upper(),
            'name':        request.form.get('name', ''),
            'price':       request.form.get('price', '0'),
            'description': request.form.get('description', ''),
            'category':    request.form.get('category', ''),
            'stock':       request.form.get('stock', '1'),
            'only_one':    'true' if request.form.get('only_one') else 'false',
            'images':      ','.join(images),
            'featured':    'true' if request.form.get('featured') else 'false',
            'created_at':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        prods = get_products()
        prods.append(product)
        save_products(prods)
        flash('Product added successfully', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', settings=s, product=None)

@app.route('/henosis-admin/products/edit/<pid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(pid):
    s        = load_settings()
    products = get_products()
    product  = next((p for p in products if p['id'] == pid), None)
    if not product:
        return redirect(url_for('admin_products'))
    if request.method == 'POST':
        imgs = [i for i in product.get('images', '').split(',') if i]
        for f in request.files.getlist('images'):
            if f and f.filename and allowed_file(f.filename):
                fn = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
                f.save(os.path.join(UPLOAD_DIR, fn))
                imgs.append(fn)
        product.update({
            'name':        request.form.get('name', product['name']),
            'price':       request.form.get('price', product['price']),
            'description': request.form.get('description', product['description']),
            'category':    request.form.get('category', product['category']),
            'stock':       request.form.get('stock', product['stock']),
            'only_one':    'true' if request.form.get('only_one') else 'false',
            'featured':    'true' if request.form.get('featured') else 'false',
            'images':      ','.join(imgs),
        })
        save_products(products)
        flash('Product updated', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', settings=s, product=product)

@app.route('/henosis-admin/products/delete/<pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    save_products([p for p in get_products() if p['id'] != pid])
    flash('Product deleted', 'success')
    return redirect(url_for('admin_products'))

@app.route('/henosis-admin/orders')
@admin_required
def admin_orders():
    orders = sorted(get_orders(), key=lambda x: x.get('created_at', ''), reverse=True)
    return render_template('admin/orders.html', settings=load_settings(), orders=orders)

@app.route('/henosis-admin/orders/update/<oid>', methods=['POST'])
@admin_required
def admin_update_order(oid):
    orders = get_orders()
    for o in orders:
        if o['id'] == oid:
            o['status']         = request.form.get('status', o['status'])
            o['payment_status'] = request.form.get('payment_status', o['payment_status'])
    save_orders(orders)
    flash('Order updated', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/henosis-admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    s = load_settings()
    if request.method == 'POST':
        for k in ['tagline', 'hero_text', 'banner_text', 'logo_text']:
            v = request.form.get(k)
            if v is not None:
                s[k] = v
        logo = request.files.get('logo_image')
        if logo and logo.filename and allowed_file(logo.filename):
            fn = f"logo_{uuid.uuid4().hex}_{secure_filename(logo.filename)}"
            logo.save(os.path.join(UPLOAD_DIR, fn))
            s['logo_image'] = fn
        save_settings(s)
        flash('Settings saved', 'success')
        return redirect(url_for('admin_settings'))
    return render_template('admin/settings.html', settings=s)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
