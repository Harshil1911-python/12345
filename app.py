import os, uuid, hashlib, secrets, io, csv, copy
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_from_directory, Response)
from werkzeug.utils import secure_filename
import db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXT = {'png','jpg','jpeg','webp','gif'}

ADMIN_EMAIL    = os.environ.get('ADMIN_EMAIL', 'henosis4india@gmail.com')
_DEFAULT_HASH  = hashlib.sha256('Henosis@2024'.encode()).hexdigest()
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD_HASH', _DEFAULT_HASH)

os.makedirs(UPLOAD_DIR, exist_ok=True)
db.init_db()

# ─── Helpers ──────────────────────────────────────────────────────────────────
def allowed_file(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXT

def save_upload(file_obj):
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        fn = f"{uuid.uuid4().hex}_{secure_filename(file_obj.filename)}"
        file_obj.save(os.path.join(UPLOAD_DIR, fn))
        return fn
    return None

def admin_required(f):
    @wraps(f)
    def d(*a,**kw):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*a,**kw)
    return d

def get_img_list(images_str):
    return [i.strip() for i in str(images_str or '').split(',') if i.strip()]

def validate_discount(code, subtotal):
    d = db.get_discount(code)
    if not d: return None, 'Invalid discount code'
    active = str(d.get('active','')).lower() in ('true','1','t')
    if not active: return None, 'Discount code is inactive'
    if int(d.get('uses_left',0)) <= 0: return None, 'Discount code has expired'
    if float(subtotal) < float(d.get('min_order',0)):
        return None, f"Minimum order ₹{d['min_order']:.0f} required for this code"
    return d, None

# ─── Context processors ───────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    """Make db helpers available in sidebar templates."""
    return {'get_reviews': db.get_all_reviews, 'get_orders': db.get_all_orders}

# ─── Public: maintenance gate ─────────────────────────────────────────────────
@app.before_request
def maintenance_gate():
    s = db.get_settings()
    if (s.get('maintenance_mode') == 'true'
            and not session.get('admin_logged_in')
            and not request.path.startswith('/henosis-admin')
            and not request.path.startswith('/uploads')
            and not request.path.startswith('/static')):
        return render_template('maintenance.html', settings=s), 503

# ─── Public routes ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    s = db.get_settings()
    p = db.get_all_products()
    featured = [x for x in p if x.get('featured')][:6]
    return render_template('index.html', settings=s, featured=featured, products=p[:8])

@app.route('/shop')
def shop():
    s    = db.get_settings()
    p    = db.get_all_products()
    cat  = request.args.get('category','')
    q    = request.args.get('q','').lower()
    sort = request.args.get('sort','newest')
    if cat: p = [x for x in p if x.get('category','').lower()==cat.lower()]
    if q:   p = [x for x in p if q in x.get('name','').lower() or q in x.get('description','').lower()]
    if sort=='price_asc':  p = sorted(p, key=lambda x: float(x.get('price',0)))
    if sort=='price_desc': p = sorted(p, key=lambda x: float(x.get('price',0)), reverse=True)
    if sort=='newest':     p = sorted(p, key=lambda x: str(x.get('created_at','')), reverse=True)
    cats = sorted({x['category'] for x in db.get_all_products() if x.get('category')})
    return render_template('shop.html', settings=s, products=p,
                           categories=cats, selected_category=cat, q=q, sort=sort)

@app.route('/product/<pid>')
def product_detail(pid):
    s = db.get_settings()
    product = db.get_product_by_id(pid)
    if not product: return redirect(url_for('shop'))
    all_p   = db.get_all_products()
    related = [x for x in all_p if x['id']!=pid and x.get('category')==product.get('category')][:4]
    reviews = db.get_reviews_for_product(pid)
    avg_rating = round(sum(int(r['rating']) for r in reviews)/len(reviews),1) if reviews else 0
    return render_template('product.html', settings=s, product=product,
                           related=related, reviews=reviews, avg_rating=avg_rating)

@app.route('/product/<pid>/review', methods=['POST'])
def submit_review(pid):
    name    = request.form.get('name','').strip()
    rating  = max(1, min(5, int(request.form.get('rating','5'))))
    comment = request.form.get('comment','').strip()
    if name and comment:
        db.create_review({'product_id':pid,'customer_name':name,'rating':rating,'comment':comment})
        flash('Thank you! Your review will appear after approval.','success')
    return redirect(url_for('product_detail', pid=pid))

@app.route('/cart')
def cart():
    return render_template('cart.html', settings=db.get_settings())

@app.route('/api/discount', methods=['POST'])
def api_discount():
    data  = request.get_json(silent=True) or {}
    code  = data.get('code','').strip()
    total = float(data.get('total',0))
    d, err = validate_discount(code, total)
    if err: return jsonify({'success':False,'error':err})
    amount = round(total * float(d['value'])/100,2) if d['discount_type']=='percent' else min(float(d['value']),total)
    return jsonify({'success':True,'amount':amount,'type':d['discount_type'],'value':d['value']})

@app.route('/checkout', methods=['GET','POST'])
def checkout():
    s = db.get_settings()
    if request.method=='POST':
        data       = request.get_json(silent=True) or {}
        cart_items = data.get('cart',[])
        cust       = data.get('customer',{})
        disc_code  = data.get('discount_code','').strip()
        if not cart_items or not cust.get('name'):
            return jsonify({'success':False,'error':'Missing data'}),400

        all_p    = db.get_all_products()
        subtotal = 0; items_str = []
        for ci in cart_items:
            p = next((x for x in all_p if x['id']==ci['id']),None)
            if p:
                qty=int(ci.get('qty',1)); price=float(p['price'])
                subtotal+=price*qty
                items_str.append(f"{p['name']} x{qty} @₹{price:.0f}")

        discount_amount = 0
        if disc_code:
            d, err = validate_discount(disc_code, subtotal)
            if d:
                discount_amount = round(subtotal*float(d['value'])/100,2) if d['discount_type']=='percent' else min(float(d['value']),subtotal)
                db.decrement_discount(disc_code)

        total = round(subtotal - discount_amount, 2)
        oid   = db.create_order({
            'customer_name':  cust.get('name',''), 'email':cust.get('email',''),
            'phone':          cust.get('phone',''), 'address':cust.get('address',''),
            'city':           cust.get('city',''),  'pincode':cust.get('pincode',''),
            'items':          ' | '.join(items_str), 'subtotal':subtotal,
            'discount_amount':discount_amount,       'total':total,
            'note':           cust.get('note',''),
        })
        db.upsert_customer(cust, total)
        for ci in cart_items:
            p = next((x for x in all_p if x['id']==ci['id']),None)
            if p:
                db.decrement_stock(p['id'], int(ci.get('qty',1)), p.get('only_one',False))
        return jsonify({'success':True,'order_id':oid})
    return render_template('checkout.html', settings=s)

@app.route('/order-success')
def order_success():
    return render_template('order_success.html', settings=db.get_settings(),
                           order_id=request.args.get('id',''))

@app.route('/about')
def about():
    return render_template('about.html', settings=db.get_settings())

@app.route('/api/products')
def api_products(): return jsonify(db.get_all_products())

# ─── Admin auth ───────────────────────────────────────────────────────────────
@app.route('/henosis-admin', methods=['GET','POST'])
def admin_login():
    if session.get('admin_logged_in'): return redirect(url_for('admin_dashboard'))
    if request.method=='POST':
        email = request.form.get('email','')
        phash = hashlib.sha256(request.form.get('password','').encode()).hexdigest()
        if email==ADMIN_EMAIL and phash==ADMIN_PASSWORD:
            session['admin_logged_in']=True; return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials','error')
    return render_template('admin/login.html')

@app.route('/henosis-admin/logout')
def admin_logout():
    session.clear(); return redirect(url_for('admin_login'))

# ─── Admin: dashboard ─────────────────────────────────────────────────────────
@app.route('/henosis-admin/dashboard')
@admin_required
def admin_dashboard():
    s         = db.get_settings()
    products  = db.get_all_products()
    orders    = db.get_all_orders()
    customers = db.get_all_customers()
    low_thresh= int(s.get('low_stock_alert','3'))
    low_stock = [x for x in products if 0 < int(x.get('stock',0)) <= low_thresh]
    reviews   = db.get_all_reviews()
    stats = {
        'products':  len(products),
        'orders':    len(orders),
        'revenue':   sum(float(x.get('total',0)) for x in orders),
        'pending':   sum(1 for x in orders if x.get('status')=='Pending'),
        'customers': len(customers),
        'reviews':   sum(1 for r in reviews if not r.get('approved')),
        'paid':      sum(float(x.get('total',0)) for x in orders if x.get('payment_status')=='Paid'),
    }
    revenue_chart = db.get_revenue_by_day(7)
    recent        = orders[:8]
    return render_template('admin/dashboard.html', settings=s, stats=stats,
                           recent_orders=recent, products=products,
                           low_stock=low_stock, revenue_chart=revenue_chart)

# ─── Admin: products ──────────────────────────────────────────────────────────
@app.route('/henosis-admin/products')
@admin_required
def admin_products():
    return render_template('admin/products.html', settings=db.get_settings(),
                           products=db.get_all_products())

@app.route('/henosis-admin/products/add', methods=['GET','POST'])
@admin_required
def admin_add_product():
    s = db.get_settings()
    if request.method=='POST':
        images = [fn for fn in [save_upload(f) for f in request.files.getlist('images')] if fn]
        db.create_product({
            'name':        request.form.get('name',''),
            'price':       float(request.form.get('price',0)),
            'description': request.form.get('description',''),
            'category':    request.form.get('category',''),
            'stock':       int(request.form.get('stock',1)),
            'only_one':    bool(request.form.get('only_one')),
            'images':      ','.join(images),
            'featured':    bool(request.form.get('featured')),
        })
        flash('Product added successfully','success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', settings=s, product=None)

@app.route('/henosis-admin/products/edit/<pid>', methods=['GET','POST'])
@admin_required
def admin_edit_product(pid):
    s = db.get_settings(); product = db.get_product_by_id(pid)
    if not product: return redirect(url_for('admin_products'))
    if request.method=='POST':
        delete_imgs = request.form.getlist('delete_image')
        imgs = [i for i in get_img_list(product.get('images','')) if i not in delete_imgs]
        new  = [fn for fn in [save_upload(f) for f in request.files.getlist('images')] if fn]
        imgs += new
        db.update_product(pid, {
            'name':        request.form.get('name', product['name']),
            'price':       float(request.form.get('price', product['price'])),
            'description': request.form.get('description', product['description']),
            'category':    request.form.get('category', product['category']),
            'stock':       int(request.form.get('stock', product['stock'])),
            'only_one':    bool(request.form.get('only_one')),
            'featured':    bool(request.form.get('featured')),
            'images':      ','.join(imgs),
        })
        flash('Product updated','success'); return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', settings=s, product=product)

@app.route('/henosis-admin/products/delete/<pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    db.delete_product(pid); flash('Product deleted','success')
    return redirect(url_for('admin_products'))

@app.route('/henosis-admin/products/duplicate/<pid>', methods=['POST'])
@admin_required
def admin_duplicate_product(pid):
    src = db.get_product_by_id(pid)
    if src:
        db.create_product({**src, 'name': 'Copy of '+src['name'],
                           'only_one': src.get('only_one',False),
                           'featured': src.get('featured',False)})
        flash('Product duplicated','success')
    return redirect(url_for('admin_products'))

# ─── Admin: orders ────────────────────────────────────────────────────────────
@app.route('/henosis-admin/orders')
@admin_required
def admin_orders():
    sf     = request.args.get('status','')
    orders = db.get_all_orders(sf if sf else None)
    return render_template('admin/orders.html', settings=db.get_settings(),
                           orders=orders, status_filter=sf)

@app.route('/henosis-admin/orders/update/<oid>', methods=['POST'])
@admin_required
def admin_update_order(oid):
    db.update_order(oid,
        request.form.get('status','Pending'),
        request.form.get('payment_status','Unpaid'),
        request.form.get('note',''))
    flash('Order updated','success'); return redirect(url_for('admin_orders'))

@app.route('/henosis-admin/orders/delete/<oid>', methods=['POST'])
@admin_required
def admin_delete_order(oid):
    db.delete_order(oid); flash('Order deleted','success')
    return redirect(url_for('admin_orders'))

@app.route('/henosis-admin/orders/export')
@admin_required
def admin_export_orders():
    orders = db.get_all_orders()
    si = io.StringIO()
    fields = ['id','customer_name','email','phone','address','city','pincode',
              'items','subtotal','discount_amount','total','status','payment_status','note','created_at']
    w = csv.DictWriter(si, fieldnames=fields, extrasaction='ignore')
    w.writeheader(); w.writerows(orders)
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':'attachment;filename=henosis_orders.csv'})

# ─── Admin: customers ─────────────────────────────────────────────────────────
@app.route('/henosis-admin/customers')
@admin_required
def admin_customers():
    return render_template('admin/customers.html', settings=db.get_settings(),
                           customers=db.get_all_customers())

@app.route('/henosis-admin/customers/delete/<cid>', methods=['POST'])
@admin_required
def admin_delete_customer(cid):
    db.delete_customer(cid); flash('Customer deleted','success')
    return redirect(url_for('admin_customers'))

@app.route('/henosis-admin/customers/export')
@admin_required
def admin_export_customers():
    customers = db.get_all_customers()
    si = io.StringIO()
    fields = ['id','name','email','phone','address','city','pincode',
              'total_orders','total_spent','created_at']
    w = csv.DictWriter(si, fieldnames=fields, extrasaction='ignore')
    w.writeheader(); w.writerows(customers)
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':'attachment;filename=henosis_customers.csv'})

# ─── Admin: discounts ─────────────────────────────────────────────────────────
@app.route('/henosis-admin/discounts')
@admin_required
def admin_discounts():
    return render_template('admin/discounts.html', settings=db.get_settings(),
                           discounts=db.get_all_discounts())

@app.route('/henosis-admin/discounts/add', methods=['POST'])
@admin_required
def admin_add_discount():
    code = request.form.get('code','').strip().upper()
    if not code: flash('Code required','error'); return redirect(url_for('admin_discounts'))
    db.create_discount({
        'code':          code,
        'discount_type': request.form.get('discount_type','percent'),
        'value':         float(request.form.get('value',10)),
        'min_order':     float(request.form.get('min_order',0)),
        'uses_left':     int(request.form.get('uses_left',100)),
    })
    flash(f'Discount code {code} created','success')
    return redirect(url_for('admin_discounts'))

@app.route('/henosis-admin/discounts/toggle/<code>', methods=['POST'])
@admin_required
def admin_toggle_discount(code):
    db.toggle_discount(code); flash('Discount updated','success')
    return redirect(url_for('admin_discounts'))

@app.route('/henosis-admin/discounts/delete/<code>', methods=['POST'])
@admin_required
def admin_delete_discount(code):
    db.delete_discount(code); flash('Discount deleted','success')
    return redirect(url_for('admin_discounts'))

# ─── Admin: reviews ───────────────────────────────────────────────────────────
@app.route('/henosis-admin/reviews')
@admin_required
def admin_reviews():
    reviews  = db.get_all_reviews()
    products = {p['id']:p['name'] for p in db.get_all_products()}
    return render_template('admin/reviews.html', settings=db.get_settings(),
                           reviews=reviews, products=products)

@app.route('/henosis-admin/reviews/approve/<rid>', methods=['POST'])
@admin_required
def admin_approve_review(rid):
    db.approve_review(rid); flash('Review approved','success')
    return redirect(url_for('admin_reviews'))

@app.route('/henosis-admin/reviews/delete/<rid>', methods=['POST'])
@admin_required
def admin_delete_review(rid):
    db.delete_review(rid); flash('Review deleted','success')
    return redirect(url_for('admin_reviews'))

# ─── Admin: settings ──────────────────────────────────────────────────────────
@app.route('/henosis-admin/settings', methods=['GET','POST'])
@admin_required
def admin_settings():
    s = db.get_settings()
    if request.method=='POST':
        tab = request.form.get('tab','brand')
        fields_map = {
            'brand':   ['logo_text','footer_text','contact_email','contact_phone',
                        'instagram_url','pinterest_url','whatsapp_number','whatsapp_chat'],
            'hero':    ['tagline','hero_text'],
            'banner':  ['banner_text','banner_active'],
            'shop':    ['free_shipping_min','currency_symbol','low_stock_alert','show_reviews'],
            'seo':     ['meta_title','meta_description','google_analytics'],
            'advanced':['maintenance_mode','popup_enabled','popup_title','popup_text','popup_cta'],
            'colors':  ['primary_color','accent_color'],
        }
        for k in fields_map.get(tab, []):
            v = request.form.get(k)
            if v is not None: s[k]=v
        # Checkboxes (not sent when unchecked)
        if tab=='banner':   s['banner_active']    = 'true' if request.form.get('banner_active') else 'false'
        if tab=='shop':     s['show_reviews']     = 'true' if request.form.get('show_reviews') else 'false'
        if tab=='brand':    s['whatsapp_chat']    = 'true' if request.form.get('whatsapp_chat') else 'false'
        if tab=='advanced': s['maintenance_mode'] = 'true' if request.form.get('maintenance_mode') else 'false'
        if tab=='advanced': s['popup_enabled']    = 'true' if request.form.get('popup_enabled') else 'false'

        # File uploads
        logo = request.files.get('logo_image')
        fn = save_upload(logo)
        if fn: s['logo_image'] = fn
        hero_img = request.files.get('hero_image')
        fn2 = save_upload(hero_img)
        if fn2: s['hero_image'] = fn2

        db.set_settings_bulk(s)
        flash('Settings saved','success')
        return redirect(url_for('admin_settings', tab=tab))
    active_tab = request.args.get('tab','brand')
    return render_template('admin/settings.html', settings=s, active_tab=active_tab)

@app.route('/henosis-admin/settings/reset-logo', methods=['POST'])
@admin_required
def admin_reset_logo():
    db.set_setting('logo_image',''); flash('Logo reset','success')
    return redirect(url_for('admin_settings'))

@app.route('/henosis-admin/settings/reset-hero', methods=['POST'])
@admin_required
def admin_reset_hero():
    db.set_setting('hero_image',''); flash('Hero image reset','success')
    return redirect(url_for('admin_settings'))

# ─── Admin: change password ───────────────────────────────────────────────────
@app.route('/henosis-admin/change-password', methods=['GET','POST'])
@admin_required
def admin_change_password():
    global ADMIN_PASSWORD
    s = db.get_settings()
    if request.method=='POST':
        current = request.form.get('current','')
        new_pw  = request.form.get('new_password','')
        confirm = request.form.get('confirm','')
        if hashlib.sha256(current.encode()).hexdigest() != ADMIN_PASSWORD:
            flash('Current password incorrect','error')
        elif len(new_pw) < 8:
            flash('Password must be at least 8 characters','error')
        elif new_pw != confirm:
            flash('Passwords do not match','error')
        else:
            ADMIN_PASSWORD = hashlib.sha256(new_pw.encode()).hexdigest()
            flash('Password changed successfully. Update ADMIN_PASSWORD_HASH env var on Render.','success')
            return redirect(url_for('admin_dashboard'))
    return render_template('admin/change_password.html', settings=s)

# ─── Admin: analytics ─────────────────────────────────────────────────────────
@app.route('/henosis-admin/analytics')
@admin_required
def admin_analytics():
    s         = db.get_settings()
    orders    = db.get_all_orders()
    products  = db.get_all_products()
    customers = db.get_all_customers()
    # Revenue by month
    from collections import defaultdict
    monthly = defaultdict(float)
    status_counts = defaultdict(int)
    category_sales = defaultdict(int)
    for o in orders:
        month = str(o.get('created_at',''))[:7]
        monthly[month] += float(o.get('total',0))
        status_counts[o.get('status','Unknown')] += 1
    for o in orders:
        for item in str(o.get('items','')).split(' | '):
            for p in products:
                if p['name'] in item:
                    category_sales[p.get('category','Other')] += 1
    stats = {
        'total_revenue':  sum(float(x.get('total',0)) for x in orders),
        'paid_revenue':   sum(float(x.get('total',0)) for x in orders if x.get('payment_status')=='Paid'),
        'avg_order':      (sum(float(x.get('total',0)) for x in orders)/len(orders)) if orders else 0,
        'total_orders':   len(orders),
        'total_customers':len(customers),
        'total_products': len(products),
        'out_of_stock':   sum(1 for p in products if int(p.get('stock',0))==0),
    }
    return render_template('admin/analytics.html', settings=s, stats=stats,
                           monthly_revenue=sorted(monthly.items()),
                           status_counts=dict(status_counts),
                           category_sales=dict(category_sales),
                           top_customers=sorted(customers, key=lambda x: float(x.get('total_spent',0)), reverse=True)[:5])

# ─── Uploads ──────────────────────────────────────────────────────────────────
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__=='__main__':
    app.run(debug=True, port=5000)
