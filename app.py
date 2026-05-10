import os, uuid, hashlib, secrets, io, csv, base64, copy
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, Response)
from werkzeug.utils import secure_filename
import db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

ADMIN_EMAIL    = os.environ.get('ADMIN_EMAIL', 'henosis4india@gmail.com')
_DEF_HASH      = hashlib.sha256('Henosis@2024'.encode()).hexdigest()
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD_HASH', _DEF_HASH)

ALLOWED_EXT = {'png','jpg','jpeg','webp','gif'}
MIME_MAP    = {'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png',
               'webp':'image/webp','gif':'image/gif'}

db.init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────
def allowed_file(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXT

def file_to_bytes(file_obj):
    return file_obj.read(), MIME_MAP.get(file_obj.filename.rsplit('.',1)[-1].lower(), 'image/jpeg')

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*a, **kw)
    return d

def validate_discount(code, subtotal):
    d = db.get_discount(code)
    if not d:                                       return None, 'Invalid discount code'
    if not d['active']:                             return None, 'This code is currently inactive'
    if d['uses_left'] <= 0:                         return None, 'This code has expired'
    if float(subtotal) < d['min_order']:
        return None, f"Minimum order ₹{d['min_order']:.0f} required"
    return d, None

def calc_discount_amount(d, subtotal):
    if d['discount_type'] == 'percent':
        return round(float(subtotal) * d['value'] / 100, 2)
    return min(d['value'], float(subtotal))

# ── Context processors ────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    return {'get_reviews': db.get_all_reviews, 'get_orders': db.get_all_orders}

# ── Image serving route ───────────────────────────────────────────────────────
@app.route('/img/<key>')
def serve_image(key):
    data, mime = db.get_image_data(key)
    if not data:
        return '', 404
    return Response(base64.b64decode(data), mimetype=mime,
                    headers={'Cache-Control':'public,max-age=31536000'})

@app.route('/pimg/<img_id>')
def serve_product_image(img_id):
    rows = db._exec(f"SELECT data,mime_type FROM product_images WHERE id={db.PH}", (img_id,), fetch='one')
    if not rows:
        return '', 404
    return Response(base64.b64decode(rows['data']), mimetype=rows['mime_type'],
                    headers={'Cache-Control':'public,max-age=31536000'})

# ── Maintenance gate ──────────────────────────────────────────────────────────
@app.before_request
def maintenance_gate():
    skip = ('/henosis-admin', '/img/', '/pimg/', '/static/', '/api/discount')
    if any(request.path.startswith(s) for s in skip):
        return
    if not session.get('admin_logged_in'):
        s = db.get_settings()
        if s.get('maintenance_mode') == 'true':
            return render_template('maintenance.html', settings=s), 503

# ── Public routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    s = db.get_settings()
    p = db.get_all_products()
    for prod in p:
        imgs = db.get_product_images(prod['id'])
        prod['thumb'] = imgs[0]['id'] if imgs else None
    featured = [x for x in p if x['featured']][:6]
    return render_template('index.html', settings=s, featured=featured, products=p[:8])

@app.route('/shop')
def shop():
    s    = db.get_settings()
    p    = db.get_all_products()
    cat  = request.args.get('category','')
    q    = request.args.get('q','').lower()
    sort = request.args.get('sort','newest')
    for prod in p:
        imgs = db.get_product_images(prod['id'])
        prod['thumb'] = imgs[0]['id'] if imgs else None
    if cat:  p = [x for x in p if x.get('category','').lower()==cat.lower()]
    if q:    p = [x for x in p if q in x.get('name','').lower() or q in x.get('description','').lower()]
    if sort=='price_asc':  p = sorted(p, key=lambda x: x['price'])
    if sort=='price_desc': p = sorted(p, key=lambda x: x['price'], reverse=True)
    cats = sorted({x['category'] for x in db.get_all_products() if x.get('category')})
    return render_template('shop.html', settings=s, products=p,
                           categories=cats, selected_category=cat, q=q, sort=sort)

@app.route('/product/<pid>')
def product_detail(pid):
    s       = db.get_settings()
    product = db.get_product_by_id(pid)
    if not product: return redirect(url_for('shop'))
    imgs    = db.get_product_images(pid)
    all_p   = db.get_all_products()
    related = []
    for rp in all_p:
        if rp['id'] != pid and rp.get('category') == product.get('category'):
            ri = db.get_product_images(rp['id'])
            rp['thumb'] = ri[0]['id'] if ri else None
            related.append(rp)
    reviews    = db.get_reviews_for_product(pid)
    avg_rating = round(sum(r['rating'] for r in reviews)/len(reviews),1) if reviews else 0
    return render_template('product.html', settings=s, product=product,
                           images=imgs, related=related[:4],
                           reviews=reviews, avg_rating=avg_rating)

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
    amount = calc_discount_amount(d, total)
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
            return jsonify({'success':False,'error':'Missing data'}), 400
        all_p    = db.get_all_products()
        subtotal = 0; items_str = []
        for ci in cart_items:
            p = next((x for x in all_p if x['id']==ci['id']), None)
            if p:
                qty=int(ci.get('qty',1)); price=float(p['price'])
                subtotal+=price*qty
                items_str.append(f"{p['name']} x{qty} @₹{price:.0f}")
        disc_amount = 0; used_code = ''
        if disc_code:
            d, err = validate_discount(disc_code, subtotal)
            if d:
                disc_amount = calc_discount_amount(d, subtotal)
                used_code   = disc_code.upper()
                db.decrement_discount(disc_code)
        total = round(subtotal - disc_amount, 2)
        oid   = db.create_order({
            'customer_name':cust.get('name',''), 'email':cust.get('email',''),
            'phone':cust.get('phone',''),        'address':cust.get('address',''),
            'city':cust.get('city',''),          'pincode':cust.get('pincode',''),
            'items':' | '.join(items_str),       'subtotal':subtotal,
            'discount_code':used_code,           'discount_amount':disc_amount,
            'total':total,                       'note':cust.get('note',''),
        })
        db.upsert_customer(cust, total)
        for ci in cart_items:
            p = next((x for x in all_p if x['id']==ci['id']), None)
            if p: db.decrement_stock(p['id'], int(ci.get('qty',1)), p['only_one'])
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
def api_products():
    p = db.get_all_products()
    for prod in p:
        imgs = db.get_product_images(prod['id'])
        prod['thumb_url'] = url_for('serve_product_image', img_id=imgs[0]['id'], _external=True) if imgs else ''
    return jsonify(p)

# ── Admin auth ────────────────────────────────────────────────────────────────
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

# ── Admin: dashboard ──────────────────────────────────────────────────────────
@app.route('/henosis-admin/dashboard')
@admin_required
def admin_dashboard():
    s         = db.get_settings()
    products  = db.get_all_products()
    orders    = db.get_all_orders()
    customers = db.get_all_customers()
    thresh    = int(s.get('low_stock_alert','3'))
    low_stock = [x for x in products if 0 < x['stock'] <= thresh]
    reviews   = db.get_all_reviews()
    stats = {
        'products':  len(products),
        'orders':    len(orders),
        'revenue':   sum(float(x.get('total',0)) for x in orders),
        'paid':      sum(float(x.get('total',0)) for x in orders if x.get('payment_status')=='Paid'),
        'pending':   sum(1 for x in orders if x.get('status')=='Pending'),
        'customers': len(customers),
        'reviews':   sum(1 for r in reviews if not r['approved']),
    }
    return render_template('admin/dashboard.html', settings=s, stats=stats,
                           recent_orders=orders[:8], products=products,
                           low_stock=low_stock, revenue_chart=db.get_revenue_by_day(7))

# ── Admin: products ───────────────────────────────────────────────────────────
@app.route('/henosis-admin/products')
@admin_required
def admin_products():
    products = db.get_all_products()
    for p in products:
        imgs = db.get_product_images(p['id'])
        p['thumb'] = imgs[0]['id'] if imgs else None
    return render_template('admin/products.html', settings=db.get_settings(), products=products)

@app.route('/henosis-admin/products/add', methods=['GET','POST'])
@admin_required
def admin_add_product():
    s = db.get_settings()
    if request.method=='POST':
        pid = db.create_product({
            'name':        request.form.get('name',''),
            'price':       float(request.form.get('price',0)),
            'description': request.form.get('description',''),
            'category':    request.form.get('category',''),
            'stock':       int(request.form.get('stock',1)),
            'only_one':    bool(request.form.get('only_one')),
            'featured':    bool(request.form.get('featured')),
        })
        files = request.files.getlist('images')
        for i, f in enumerate(files):
            if f and f.filename and allowed_file(f.filename):
                b, mime = file_to_bytes(f)
                db.save_product_image(pid, b, mime, sort_order=i)
        flash('Product added successfully','success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', settings=s, product=None, images=[])

@app.route('/henosis-admin/products/edit/<pid>', methods=['GET','POST'])
@admin_required
def admin_edit_product(pid):
    s = db.get_settings(); product = db.get_product_by_id(pid)
    if not product: return redirect(url_for('admin_products'))
    existing_images = db.get_product_images(pid)
    if request.method=='POST':
        for del_id in request.form.getlist('delete_image'):
            db.delete_product_image(del_id)
        db.update_product(pid, {
            'name':        request.form.get('name', product['name']),
            'price':       float(request.form.get('price', product['price'])),
            'description': request.form.get('description', product['description']),
            'category':    request.form.get('category', product['category']),
            'stock':       int(request.form.get('stock', product['stock'])),
            'only_one':    bool(request.form.get('only_one')),
            'featured':    bool(request.form.get('featured')),
        })
        remaining = db.get_product_images(pid)
        next_order = len(remaining)
        for f in request.files.getlist('images'):
            if f and f.filename and allowed_file(f.filename):
                b, mime = file_to_bytes(f)
                db.save_product_image(pid, b, mime, sort_order=next_order)
                next_order += 1
        flash('Product updated','success'); return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', settings=s, product=product, images=existing_images)

@app.route('/henosis-admin/products/delete/<pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    db.delete_all_product_images(pid); db.delete_product(pid)
    flash('Product deleted','success'); return redirect(url_for('admin_products'))

@app.route('/henosis-admin/products/duplicate/<pid>', methods=['POST'])
@admin_required
def admin_duplicate_product(pid):
    src = db.get_product_by_id(pid)
    if src:
        new_pid = db.create_product({**src, 'name':'Copy of '+src['name']})
        for img in db.get_product_images(pid):
            db._exec(f"INSERT INTO product_images(id,product_id,data,mime_type,sort_order) VALUES({db.PH},{db.PH},{db.PH},{db.PH},{db.PH})",
                     (str(uuid.uuid4()), new_pid, img['data'], img['mime_type'], img.get('sort_order',0)), commit=True)
        flash('Product duplicated','success')
    return redirect(url_for('admin_products'))

# ── Admin: orders ─────────────────────────────────────────────────────────────
@app.route('/henosis-admin/orders')
@admin_required
def admin_orders():
    sf = request.args.get('status','')
    orders = db.get_all_orders(sf if sf else None)
    return render_template('admin/orders.html', settings=db.get_settings(),
                           orders=orders, status_filter=sf)

@app.route('/henosis-admin/orders/update/<oid>', methods=['POST'])
@admin_required
def admin_update_order(oid):
    db.update_order(oid, request.form.get('status','Pending'),
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
              'items','subtotal','discount_code','discount_amount','total',
              'status','payment_status','note','created_at']
    w = csv.DictWriter(si, fieldnames=fields, extrasaction='ignore')
    w.writeheader(); w.writerows(orders)
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':'attachment;filename=henosis_orders.csv'})

# ── Admin: customers ──────────────────────────────────────────────────────────
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
    si = io.StringIO()
    w  = csv.DictWriter(si, fieldnames=['id','name','email','phone','address','city',
                        'pincode','total_orders','total_spent','created_at'], extrasaction='ignore')
    w.writeheader(); w.writerows(db.get_all_customers())
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':'attachment;filename=henosis_customers.csv'})

# ── Admin: discounts ──────────────────────────────────────────────────────────
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
    db.create_discount({'code':code,'discount_type':request.form.get('discount_type','percent'),
                        'value':float(request.form.get('value',10)),
                        'min_order':float(request.form.get('min_order',0)),
                        'uses_left':int(request.form.get('uses_left',100))})
    flash(f'Code {code} created','success'); return redirect(url_for('admin_discounts'))

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

# ── Admin: reviews ────────────────────────────────────────────────────────────
@app.route('/henosis-admin/reviews')
@admin_required
def admin_reviews():
    products = {p['id']:p['name'] for p in db.get_all_products()}
    return render_template('admin/reviews.html', settings=db.get_settings(),
                           reviews=db.get_all_reviews(), products=products)

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

# ── Admin: analytics ──────────────────────────────────────────────────────────
@app.route('/henosis-admin/analytics')
@admin_required
def admin_analytics():
    from collections import defaultdict
    s         = db.get_settings()
    orders    = db.get_all_orders()
    products  = db.get_all_products()
    customers = db.get_all_customers()
    monthly   = defaultdict(float)
    status_c  = defaultdict(int)
    cat_sales = defaultdict(int)
    for o in orders:
        monthly[str(o.get('created_at',''))[:7]] += float(o.get('total',0))
        status_c[o.get('status','Unknown')] += 1
    for o in orders:
        for item in str(o.get('items','')).split(' | '):
            for p in products:
                if p['name'] in item:
                    cat_sales[p.get('category','Other')] += 1
    stats = {
        'total_revenue':  sum(float(x.get('total',0)) for x in orders),
        'paid_revenue':   sum(float(x.get('total',0)) for x in orders if x.get('payment_status')=='Paid'),
        'avg_order':      (sum(float(x.get('total',0)) for x in orders)/len(orders)) if orders else 0,
        'total_orders':   len(orders),
        'total_customers':len(customers),
        'total_products': len(products),
        'out_of_stock':   sum(1 for p in products if p['stock']==0),
    }
    return render_template('admin/analytics.html', settings=s, stats=stats,
                           monthly_revenue=sorted(monthly.items()),
                           status_counts=dict(status_c), category_sales=dict(cat_sales),
                           top_customers=sorted(customers, key=lambda x:float(x.get('total_spent',0)), reverse=True)[:5])

# ── Admin: settings ───────────────────────────────────────────────────────────
@app.route('/henosis-admin/settings', methods=['GET','POST'])
@admin_required
def admin_settings():
    s = db.get_settings()
    if request.method=='POST':
        tab = request.form.get('tab','brand')
        tab_fields = {
            'brand':   ['logo_text','footer_text','contact_email','contact_phone',
                        'instagram_url','pinterest_url','whatsapp_number'],
            'hero':    ['tagline','hero_text'],
            'banner':  ['banner_text'],
            'shop':    ['free_shipping_min','currency_symbol','low_stock_alert'],
            'colors':  ['primary_color','accent_color'],
            'seo':     ['meta_title','meta_description','google_analytics'],
            'advanced':['popup_title','popup_text','popup_cta'],
        }
        for k in tab_fields.get(tab, []):
            v = request.form.get(k)
            if v is not None: s[k] = v
        # Checkboxes
        bools = {'brand':['whatsapp_chat'],'banner':['banner_active'],
                 'shop':['show_reviews'],'advanced':['maintenance_mode','popup_enabled']}
        for k in bools.get(tab,[]):
            s[k] = 'true' if request.form.get(k) else 'false'
        # Image uploads — store in DB
        logo_file = request.files.get('logo_image')
        if logo_file and logo_file.filename and allowed_file(logo_file.filename):
            b, mime = file_to_bytes(logo_file)
            key = db.save_image_to_db(b, mime)
            s['logo_image_key'] = key
        hero_file = request.files.get('hero_image')
        if hero_file and hero_file.filename and allowed_file(hero_file.filename):
            b, mime = file_to_bytes(hero_file)
            key = db.save_image_to_db(b, mime)
            s['hero_image_key'] = key
        db.set_settings_bulk(s)
        flash('Settings saved','success')
        return redirect(url_for('admin_settings', tab=tab))
    return render_template('admin/settings.html', settings=s,
                           active_tab=request.args.get('tab','brand'))

@app.route('/henosis-admin/settings/reset-logo', methods=['POST'])
@admin_required
def admin_reset_logo():
    db.set_setting('logo_image_key',''); flash('Logo reset','success')
    return redirect(url_for('admin_settings'))

@app.route('/henosis-admin/settings/reset-hero', methods=['POST'])
@admin_required
def admin_reset_hero():
    db.set_setting('hero_image_key',''); flash('Hero image reset','success')
    return redirect(url_for('admin_settings'))

# ── Admin: change password ────────────────────────────────────────────────────
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
            flash('Must be at least 8 characters','error')
        elif new_pw != confirm:
            flash('Passwords do not match','error')
        else:
            ADMIN_PASSWORD = hashlib.sha256(new_pw.encode()).hexdigest()
            flash(f'Password changed! Set ADMIN_PASSWORD_HASH={ADMIN_PASSWORD} on Render.','success')
            return redirect(url_for('admin_dashboard'))
    return render_template('admin/change_password.html', settings=s)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
