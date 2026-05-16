"""
app.py — Henosis Flask Application
All routes, admin panel, image serving, checkout, notifications.
"""
import os, uuid, hashlib, secrets, io, csv, base64, json
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, Response, abort)
from werkzeug.utils import secure_filename
import db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

ADMIN_EMAIL    = os.environ.get('ADMIN_EMAIL', 'henosis4india@gmail.com')
_DEF_HASH      = hashlib.sha256('Henosis@2024'.encode()).hexdigest()
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD_HASH', _DEF_HASH)
ALLOWED_EXT    = {'png','jpg','jpeg','webp','gif'}
MIME_MAP       = {'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','webp':'image/webp','gif':'image/gif'}

db.init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────
def allowed_file(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXT

def read_upload(f):
    raw  = f.read()
    mime = MIME_MAP.get(f.filename.rsplit('.',1)[-1].lower(), 'image/jpeg')
    return raw, mime

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*a, **kw)
    return d

def validate_discount(code, subtotal):
    d = db.get_discount(code)
    if not d:              return None, 'Invalid discount code'
    if not d['active']:    return None, 'This code is currently inactive'
    if d['uses_left'] <= 0: return None, 'This code has expired'
    if float(subtotal) < d['min_order']:
        return None, f"Minimum order ₹{d['min_order']:.0f} required"
    return d, None

def calc_discount(d, subtotal):
    return round(float(subtotal)*d['value']/100, 2) if d['discount_type']=='percent' else min(d['value'], float(subtotal))

def send_email(to, subject, body_html):
    """Send email via SMTP if configured."""
    s = db.get_settings()
    if s.get('email_notifications') != 'true': return False
    host = s.get('smtp_host',''); user = s.get('smtp_user',''); pw = s.get('smtp_pass','')
    if not (host and user and pw): return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = s.get('smtp_from', user)
        msg['To']      = to
        msg.attach(MIMEText(body_html, 'html'))
        with smtplib.SMTP(host, int(s.get('smtp_port', 587))) as srv:
            srv.starttls()
            srv.login(user, pw)
            srv.sendmail(msg['From'], [to], msg.as_string())
        return True
    except Exception as e:
        db.log_activity('Email Error', str(e))
        return False

# ── Context processors ────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    return {
        'get_all_reviews':      db.get_all_reviews,
        'get_reviews':          db.get_all_reviews,
        'get_all_orders':       db.get_all_orders,
        'get_orders':           db.get_all_orders,
        'count_unread':         db.count_unread_notifications,
        'get_ads':              db.get_ads_for_position,
    }

# ── Image routes ──────────────────────────────────────────────────────────────
@app.route('/img/<key>')
def serve_image(key):
    data, mime = db.get_site_image(key)
    if not data: return '', 404
    return Response(base64.b64decode(data), mimetype=mime,
                    headers={'Cache-Control':'public,max-age=31536000,immutable'})

@app.route('/pimg/<img_id>')
def serve_product_image(img_id):
    r = db._exec(f"SELECT data,mime_type FROM product_images WHERE id={db.PH}", (img_id,), fetch='one')
    if not r: return '', 404
    return Response(base64.b64decode(r['data']), mimetype=r['mime_type'],
                    headers={'Cache-Control':'public,max-age=31536000,immutable'})

# ── Maintenance gate ──────────────────────────────────────────────────────────
@app.before_request
def maintenance_gate():
    skip = ('/henosis-admin','/img/','/pimg/','/static/','/api/')
    if any(request.path.startswith(s) for s in skip): return
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
    db.track_view(pid)
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
                           images=imgs, related=related[:4], reviews=reviews, avg_rating=avg_rating)

@app.route('/product/<pid>/review', methods=['POST'])
def submit_review(pid):
    name    = request.form.get('name','').strip()
    rating  = max(1, min(5, int(request.form.get('rating','5'))))
    comment = request.form.get('comment','').strip()
    if name and comment:
        db.create_review({'product_id':pid,'customer_name':name,'rating':rating,'comment':comment})
        flash('Thank you! Your review will appear after approval.','success')
    return redirect(url_for('product_detail', pid=pid))

@app.route('/notify-restock/<pid>', methods=['POST'])
def notify_restock(pid):
    email = request.form.get('email','').strip()
    if email:
        db.add_restock_notify(pid, email)
        flash("We'll notify you when this is back in stock.",'success')
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
    amount = calc_discount(d, total)
    return jsonify({'success':True,'amount':amount,'type':d['discount_type'],'value':d['value']})

@app.route('/checkout', methods=['GET','POST'])
def checkout():
    s = db.get_settings()
    if request.method == 'POST':
        data       = request.get_json(silent=True) or {}
        cart_items = data.get('cart',[])
        cust       = data.get('customer',{})
        disc_code  = data.get('discount_code','').strip()
        if not cart_items or not cust.get('name'):
            return jsonify({'success':False,'error':'Missing data'}), 400
        if db.is_blocked(cust.get('email','')):
            return jsonify({'success':False,'error':'Unable to process order'}), 403
        all_p    = db.get_all_products()
        subtotal = 0; items_str = []
        for ci in cart_items:
            p = next((x for x in all_p if x['id']==ci['id']), None)
            if p:
                qty=int(ci.get('qty',1)); price=float(p['price'])
                subtotal+=price*qty
                items_str.append(f"{p['name']} x{qty} @₹{price:.0f}")
        disc_amount=0; used_code=''
        if disc_code:
            d,err = validate_discount(disc_code, subtotal)
            if d:
                disc_amount = calc_discount(d, subtotal)
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
        # Admin notification
        db.add_notification('order', f'New Order #{oid}',
            f"{cust.get('name','')} — ₹{total:,.0f}", f'/henosis-admin/orders')
        db.log_activity('New Order', f"#{oid} ₹{total:,.0f} by {cust.get('name','')}")
        # Email confirmation
        s2 = db.get_settings()
        if s2.get('email_notifications')=='true':
            email_html = f"""<h2>Order Confirmed #{oid}</h2><p>Hi {cust.get('name','')},</p>
            <p>Your order has been placed successfully.</p>
            <p><strong>Items:</strong> {' | '.join(items_str)}</p>
            <p><strong>Total:</strong> ₹{total:,.0f}</p>
            <p>We'll contact you soon with shipping details.</p>
            <p>— {s2.get('logo_text','HENOSIS')} Team</p>"""
            send_email(cust.get('email',''), f'Order Confirmed #{oid}', email_html)
            admin_html = f"<h2>New Order #{oid}</h2><p>{cust.get('name','')} ({cust.get('phone','')})</p><p>₹{total:,.0f}</p><p>{' | '.join(items_str)}</p>"
            send_email(s2.get('contact_email',''), f'🛍️ New Order #{oid} — ₹{total:,.0f}', admin_html)
        return jsonify({'success':True,'order_id':oid})
    return render_template('checkout.html', settings=s)

@app.route('/order-success')
def order_success():
    oid = request.args.get('id','')
    return render_template('order_success.html', settings=db.get_settings(), order_id=oid)

@app.route('/about')
def about():
    return render_template('about.html', settings=db.get_settings())

@app.route('/page/<slug>')
def custom_page(slug):
    s    = db.get_settings()
    page = db.get_page_by_slug(slug)
    if not page or not page['published']: abort(404)
    return render_template('custom_page.html', settings=s, page=page)

@app.route('/api/products')
def api_products():
    p = db.get_all_products()
    for prod in p:
        imgs = db.get_product_images(prod['id'])
        prod['thumb_url'] = url_for('serve_product_image', img_id=imgs[0]['id'], _external=True) if imgs else ''
    return jsonify(p)

# ── Admin: auth ───────────────────────────────────────────────────────────────
@app.route('/henosis-admin', methods=['GET','POST'])
def admin_login():
    if session.get('admin_logged_in'): return redirect(url_for('admin_dashboard'))
    if request.method=='POST':
        email = request.form.get('email','')
        phash = hashlib.sha256(request.form.get('password','').encode()).hexdigest()
        if email==ADMIN_EMAIL and phash==ADMIN_PASSWORD:
            session['admin_logged_in']=True
            db.log_activity('Admin Login')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials','error')
    return render_template('admin/login.html')

@app.route('/henosis-admin/logout')
def admin_logout():
    db.log_activity('Admin Logout')
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
    total_rev = sum(float(o.get('total',0)) for o in orders)
    paid_rev  = sum(float(o.get('total',0)) for o in orders if o.get('payment_status')=='Paid')
    expenses  = db.get_total_expenses()
    stats = {
        'products':  len(products),
        'orders':    len(orders),
        'revenue':   total_rev,
        'paid':      paid_rev,
        'pending':   sum(1 for o in orders if o.get('status')=='Pending'),
        'customers': len(customers),
        'reviews':   sum(1 for r in reviews if not r['approved']),
        'profit':    paid_rev - expenses,
        'expenses':  expenses,
    }
    notifications = db.get_notifications(10)
    return render_template('admin/dashboard.html', settings=s, stats=stats,
                           recent_orders=orders[:8], products=products,
                           low_stock=low_stock, revenue_chart=db.revenue_by_day(7),
                           notifications=notifications)

@app.route('/henosis-admin/notifications/read', methods=['POST'])
@admin_required
def admin_mark_notifications_read():
    db.mark_all_notifications_read()
    return jsonify({'ok':True})

# ── Admin: products ───────────────────────────────────────────────────────────
@app.route('/henosis-admin/products')
@admin_required
def admin_products():
    products = db.get_all_products()
    view_counts = db.get_product_view_counts()
    for p in products:
        imgs = db.get_product_images(p['id'])
        p['thumb']  = imgs[0]['id'] if imgs else None
        p['views']  = view_counts.get(p['id'], 0)
        p['img_count'] = len(imgs)
    return render_template('admin/products.html', settings=db.get_settings(), products=products)

@app.route('/henosis-admin/products/add', methods=['GET','POST'])
@admin_required
def admin_add_product():
    s = db.get_settings()
    if request.method=='POST':
        pid = db.create_product({
            'name':             request.form.get('name',''),
            'price':            float(request.form.get('price',0) or 0),
            'description':      request.form.get('description',''),
            'category':         request.form.get('category',''),
            'stock':            int(request.form.get('stock',1) or 1),
            'only_one':         bool(request.form.get('only_one')),
            'featured':         bool(request.form.get('featured')),
            'material':         request.form.get('material',''),
            'dimensions':       request.form.get('dimensions',''),
            'care_instructions':request.form.get('care_instructions',''),
            'meta_title':       request.form.get('meta_title',''),
            'meta_description': request.form.get('meta_description',''),
        })
        for i,f in enumerate(request.files.getlist('images')):
            if f and f.filename and allowed_file(f.filename):
                raw, mime = read_upload(f)
                db.save_product_image(pid, raw, mime, sort_order=i)
        db.log_activity('Product Created', request.form.get('name',''))
        db.add_notification('product','Product Added',request.form.get('name',''),f'/henosis-admin/products/edit/{pid}')
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
            'name':             request.form.get('name', product['name']),
            'price':            float(request.form.get('price', product['price']) or 0),
            'description':      request.form.get('description', product['description']),
            'category':         request.form.get('category', product['category']),
            'stock':            int(request.form.get('stock', product['stock']) or 0),
            'only_one':         bool(request.form.get('only_one')),
            'featured':         bool(request.form.get('featured')),
            'material':         request.form.get('material',''),
            'dimensions':       request.form.get('dimensions',''),
            'care_instructions':request.form.get('care_instructions',''),
            'meta_title':       request.form.get('meta_title',''),
            'meta_description': request.form.get('meta_description',''),
        })
        remaining = db.get_product_images(pid)
        next_order = len(remaining)
        for f in request.files.getlist('images'):
            if f and f.filename and allowed_file(f.filename):
                raw, mime = read_upload(f)
                db.save_product_image(pid, raw, mime, sort_order=next_order)
                next_order += 1
        db.log_activity('Product Updated', product['name'])
        flash('Product updated','success'); return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', settings=s, product=product, images=existing_images)

@app.route('/henosis-admin/products/sort', methods=['POST'])
@admin_required
def admin_sort_products():
    order = request.get_json(silent=True) or {}
    for pid, sort in order.items():
        db.update_product_sort(pid, int(sort))
    return jsonify({'ok':True})

@app.route('/henosis-admin/products/delete/<pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    p = db.get_product_by_id(pid)
    db.delete_all_product_images(pid); db.delete_product(pid)
    db.log_activity('Product Deleted', p['name'] if p else pid)
    flash('Product deleted','success'); return redirect(url_for('admin_products'))

@app.route('/henosis-admin/products/duplicate/<pid>', methods=['POST'])
@admin_required
def admin_duplicate_product(pid):
    src = db.get_product_by_id(pid)
    if src:
        new_pid = db.create_product({**src, 'name':'Copy of '+src['name']})
        for img in db.get_product_images(pid):
            db._exec(f"INSERT INTO product_images(id,product_id,data,mime_type,sort_order,created_at) VALUES({db.PH},{db.PH},{db.PH},{db.PH},{db.PH},{db.PH})",
                     (str(uuid.uuid4()), new_pid, img['data'], img['mime_type'], img.get('sort_order',0), datetime.now()), commit=True)
        db.log_activity('Product Duplicated', src['name'])
        flash('Product duplicated','success')
    return redirect(url_for('admin_products'))

# ── Admin: orders ─────────────────────────────────────────────────────────────
@app.route('/henosis-admin/orders')
@admin_required
def admin_orders():
    sf = request.args.get('status','')
    return render_template('admin/orders.html', settings=db.get_settings(),
                           orders=db.get_all_orders(sf or None), status_filter=sf)

@app.route('/henosis-admin/orders/<oid>')
@admin_required
def admin_order_detail(oid):
    order    = db.get_order_by_id(oid)
    if not order: return redirect(url_for('admin_orders'))
    timeline = db.get_order_timeline(oid)
    return render_template('admin/order_detail.html', settings=db.get_settings(),
                           order=order, timeline=timeline)

@app.route('/henosis-admin/orders/update/<oid>', methods=['POST'])
@admin_required
def admin_update_order(oid):
    db.update_order(oid, request.form.get('status','Pending'),
                    request.form.get('payment_status','Unpaid'),
                    request.form.get('admin_note',''),
                    request.form.get('tracking_number',''))
    db.log_activity('Order Updated', f'#{oid} → {request.form.get("status","")}')
    flash('Order updated','success')
    return redirect(request.referrer or url_for('admin_orders'))

@app.route('/henosis-admin/orders/delete/<oid>', methods=['POST'])
@admin_required
def admin_delete_order(oid):
    db.delete_order(oid); db.log_activity('Order Deleted', f'#{oid}')
    flash('Order deleted','success'); return redirect(url_for('admin_orders'))

@app.route('/henosis-admin/orders/bulk-update', methods=['POST'])
@admin_required
def admin_bulk_orders():
    ids    = request.form.getlist('order_ids')
    status = request.form.get('bulk_status','')
    if ids and status:
        for oid in ids:
            o = db.get_order_by_id(oid)
            if o: db.update_order(oid, status, o.get('payment_status','Unpaid'), o.get('admin_note',''), o.get('tracking_number',''))
        flash(f'{len(ids)} orders updated to {status}','success')
    return redirect(url_for('admin_orders'))

@app.route('/henosis-admin/orders/export')
@admin_required
def admin_export_orders():
    orders = db.get_all_orders()
    si     = io.StringIO()
    fields = ['id','customer_name','email','phone','address','city','pincode','items',
              'subtotal','discount_code','discount_amount','total','status','payment_status',
              'note','admin_note','tracking_number','created_at']
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

@app.route('/henosis-admin/customers/<cid>')
@admin_required
def admin_customer_detail(cid):
    customer = db.get_customer_by_id(cid)
    if not customer: return redirect(url_for('admin_customers'))
    orders   = [o for o in db.get_all_orders() if o.get('email')==customer.get('email')]
    return render_template('admin/customer_detail.html', settings=db.get_settings(),
                           customer=customer, orders=orders)

@app.route('/henosis-admin/customers/update/<cid>', methods=['POST'])
@admin_required
def admin_update_customer(cid):
    db.update_customer_notes(cid, request.form.get('tags',''),
                             request.form.get('private_note',''),
                             bool(request.form.get('blocked')))
    db.log_activity('Customer Updated', cid)
    flash('Customer updated','success')
    return redirect(url_for('admin_customer_detail', cid=cid))

@app.route('/henosis-admin/customers/delete/<cid>', methods=['POST'])
@admin_required
def admin_delete_customer(cid):
    db.delete_customer(cid); db.log_activity('Customer Deleted', cid)
    flash('Customer deleted','success'); return redirect(url_for('admin_customers'))

@app.route('/henosis-admin/customers/export')
@admin_required
def admin_export_customers():
    si = io.StringIO()
    w  = csv.DictWriter(si, fieldnames=['id','name','email','phone','address','city',
                        'pincode','total_orders','total_spent','tags','created_at'], extrasaction='ignore')
    w.writeheader(); w.writerows(db.get_all_customers())
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':'attachment;filename=henosis_customers.csv'})

# ── Admin: discounts ──────────────────────────────────────────────────────────
@app.route('/henosis-admin/discounts')
@admin_required
def admin_discounts():
    return render_template('admin/discounts.html', settings=db.get_settings(), discounts=db.get_all_discounts())

@app.route('/henosis-admin/discounts/add', methods=['POST'])
@admin_required
def admin_add_discount():
    code = request.form.get('code','').strip().upper()
    if not code: flash('Code required','error'); return redirect(url_for('admin_discounts'))
    db.create_discount({'code':code,'discount_type':request.form.get('discount_type','percent'),
                        'value':float(request.form.get('value',10) or 10),
                        'min_order':float(request.form.get('min_order',0) or 0),
                        'uses_left':int(request.form.get('uses_left',100) or 100)})
    db.log_activity('Discount Created', code)
    flash(f'Code {code} created','success'); return redirect(url_for('admin_discounts'))

@app.route('/henosis-admin/discounts/toggle/<code>', methods=['POST'])
@admin_required
def admin_toggle_discount(code):
    db.toggle_discount(code); flash('Discount updated','success')
    return redirect(url_for('admin_discounts'))

@app.route('/henosis-admin/discounts/delete/<code>', methods=['POST'])
@admin_required
def admin_delete_discount(code):
    db.delete_discount(code); db.log_activity('Discount Deleted', code)
    flash('Discount deleted','success'); return redirect(url_for('admin_discounts'))

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

# ── Admin: pages ──────────────────────────────────────────────────────────────
@app.route('/henosis-admin/pages')
@admin_required
def admin_pages():
    return render_template('admin/pages.html', settings=db.get_settings(), pages=db.get_all_pages())

@app.route('/henosis-admin/pages/save', methods=['POST'])
@admin_required
def admin_save_page():
    pid = db.save_page({'id':request.form.get('id',''),'title':request.form.get('title',''),
                        'slug':request.form.get('slug',''),'content':request.form.get('content',''),
                        'published':bool(request.form.get('published'))})
    db.log_activity('Page Saved', request.form.get('title',''))
    flash('Page saved','success'); return redirect(url_for('admin_pages'))

@app.route('/henosis-admin/pages/delete/<pid>', methods=['POST'])
@admin_required
def admin_delete_page(pid):
    db.delete_page(pid); flash('Page deleted','success')
    return redirect(url_for('admin_pages'))

# ── Admin: expenses ───────────────────────────────────────────────────────────
@app.route('/henosis-admin/expenses')
@admin_required
def admin_expenses():
    expenses = db.get_all_expenses()
    total    = db.get_total_expenses()
    orders   = db.get_all_orders()
    revenue  = sum(float(o.get('total',0)) for o in orders if o.get('payment_status')=='Paid')
    return render_template('admin/expenses.html', settings=db.get_settings(),
                           expenses=expenses, total=total, revenue=revenue, profit=revenue-total)

@app.route('/henosis-admin/expenses/add', methods=['POST'])
@admin_required
def admin_add_expense():
    db.create_expense({'description':request.form.get('description',''),
                       'amount':float(request.form.get('amount',0) or 0),
                       'category':request.form.get('category','Other'),
                       'expense_date':request.form.get('expense_date','')})
    db.log_activity('Expense Added', request.form.get('description',''))
    flash('Expense recorded','success'); return redirect(url_for('admin_expenses'))

@app.route('/henosis-admin/expenses/delete/<eid>', methods=['POST'])
@admin_required
def admin_delete_expense(eid):
    db.delete_expense(eid); flash('Expense deleted','success')
    return redirect(url_for('admin_expenses'))

# ── Admin: analytics ──────────────────────────────────────────────────────────
@app.route('/henosis-admin/analytics')
@admin_required
def admin_analytics():
    from collections import defaultdict
    s         = db.get_settings()
    orders    = db.get_all_orders()
    products  = db.get_all_products()
    customers = db.get_all_customers()
    expenses  = db.get_total_expenses()
    monthly   = defaultdict(float); status_c = defaultdict(int); cat_s = defaultdict(int)
    for o in orders:
        monthly[str(o.get('created_at',''))[:7]] += float(o.get('total',0))
        status_c[o.get('status','Unknown')] += 1
    for o in orders:
        for item in str(o.get('items','')).split(' | '):
            for p in products:
                if p['name'] in item: cat_s[p.get('category','Other')] += 1
    view_counts = db.get_product_view_counts()
    top_by_views = sorted([(p, view_counts.get(p['id'],0)) for p in products], key=lambda x: x[1], reverse=True)[:5]
    total_rev  = sum(float(o.get('total',0)) for o in orders)
    paid_rev   = sum(float(o.get('total',0)) for o in orders if o.get('payment_status')=='Paid')
    stats = {
        'total_revenue':   total_rev, 'paid_revenue': paid_rev, 'expenses': expenses,
        'profit':          paid_rev - expenses,
        'avg_order':       (total_rev/len(orders)) if orders else 0,
        'total_orders':    len(orders), 'total_customers': len(customers),
        'total_products':  len(products), 'out_of_stock': sum(1 for p in products if p['stock']==0),
    }
    return render_template('admin/analytics.html', settings=s, stats=stats,
                           monthly_revenue=sorted(monthly.items()),
                           status_counts=dict(status_c), category_sales=dict(cat_s),
                           top_customers=sorted(customers, key=lambda x: float(x.get('total_spent',0)), reverse=True)[:5],
                           top_by_views=top_by_views)

# ── Admin: settings ───────────────────────────────────────────────────────────
@app.route('/henosis-admin/settings', methods=['GET','POST'])
@admin_required
def admin_settings():
    s = db.get_settings()
    if request.method=='POST':
        tab = request.form.get('tab','brand')
        fields = {
            'brand':   ['logo_text','footer_text','contact_email','contact_phone','instagram_url','pinterest_url','whatsapp_number','admin_whatsapp'],
            'hero':    ['tagline','hero_text'],
            'banner':  ['banner_text'],
            'shop':    ['free_shipping_min','currency_symbol','low_stock_alert'],
            'colors':  ['primary_color','accent_color'],
            'seo':     ['meta_title','meta_description','google_analytics'],
            'email':   ['smtp_host','smtp_port','smtp_user','smtp_pass','smtp_from'],
            'advanced':['popup_title','popup_text','popup_cta'],
        }
        for k in fields.get(tab,[]):
            v = request.form.get(k)
            if v is not None: s[k]=v
        bools = {
            'brand':   ['whatsapp_chat'],
            'banner':  ['banner_active'],
            'shop':    ['show_reviews','gst_enabled'],
            'email':   ['email_notifications'],
            'advanced':['maintenance_mode','popup_enabled'],
        }
        for k in bools.get(tab,[]):
            s[k] = 'true' if request.form.get(k) else 'false'
        if tab == 'shop':
            s['gst_percent'] = request.form.get('gst_percent', s.get('gst_percent','18'))
        logo = request.files.get('logo_image')
        if logo and logo.filename and allowed_file(logo.filename):
            raw, mime = read_upload(logo); s['logo_image_key'] = db.save_site_image(raw, mime)
        hero_img = request.files.get('hero_image')
        if hero_img and hero_img.filename and allowed_file(hero_img.filename):
            raw, mime = read_upload(hero_img); s['hero_image_key'] = db.save_site_image(raw, mime)
        db.save_settings_bulk(s)
        db.log_activity('Settings Updated', tab)
        flash('Settings saved','success')
        return redirect(url_for('admin_settings', tab=tab))
    return render_template('admin/settings.html', settings=s, active_tab=request.args.get('tab','brand'))

@app.route('/henosis-admin/settings/reset-logo', methods=['POST'])
@admin_required
def admin_reset_logo():
    db.save_setting('logo_image_key',''); flash('Logo reset','success')
    return redirect(url_for('admin_settings'))

@app.route('/henosis-admin/settings/reset-hero', methods=['POST'])
@admin_required
def admin_reset_hero():
    db.save_setting('hero_image_key',''); flash('Hero image reset','success')
    return redirect(url_for('admin_settings', tab='hero'))

# ── Admin: activity log ───────────────────────────────────────────────────────
@app.route('/henosis-admin/activity')
@admin_required
def admin_activity():
    return render_template('admin/activity.html', settings=db.get_settings(),
                           logs=db.get_activity_log(200))

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
            new_hash = hashlib.sha256(new_pw.encode()).hexdigest()
            ADMIN_PASSWORD = new_hash
            db.log_activity('Password Changed')
            flash(f'Password changed! Set this as ADMIN_PASSWORD_HASH on Render: {new_hash}','success')
            return redirect(url_for('admin_dashboard'))
    return render_template('admin/change_password.html', settings=s)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

# ── Admin: quick search API ───────────────────────────────────────────────────
@app.route('/henosis-admin/search')
@admin_required
def admin_search():
    q = request.args.get('q','').lower().strip()
    if not q:
        return jsonify({'products':[],'orders':[],'customers':[]})
    products  = [p for p in db.get_all_products()
                 if q in p.get('name','').lower() or q in p.get('category','').lower()][:5]
    orders    = [o for o in db.get_all_orders()
                 if q in o.get('id','').lower() or q in o.get('customer_name','').lower()
                 or q in o.get('email','').lower()][:5]
    customers = [c for c in db.get_all_customers()
                 if q in c.get('name','').lower() or q in c.get('email','').lower()
                 or q in c.get('phone','').lower()][:5]
    return jsonify({
        'products':  [{'id':p['id'],'name':p['name'],'price':p['price'],'url':url_for('admin_edit_product',pid=p['id'])} for p in products],
        'orders':    [{'id':o['id'],'name':o['customer_name'],'total':o['total'],'url':url_for('admin_order_detail',oid=o['id'])} for o in orders],
        'customers': [{'id':c['id'],'name':c['name'],'email':c['email'],'url':url_for('admin_customer_detail',cid=c['id'])} for c in customers],
    })

# ── Admin: AI product description ────────────────────────────────────────────
@app.route('/henosis-admin/ai-description', methods=['POST'])
@admin_required
def admin_ai_description():
    """Generate product description using Claude API."""
    data     = request.get_json(silent=True) or {}
    name     = data.get('name','')
    category = data.get('category','')
    material = data.get('material','')
    keywords = data.get('keywords','')
    if not name:
        return jsonify({'error': 'Product name required'}), 400
    try:
        import urllib.request, urllib.error
        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 300,
            "messages": [{
                "role": "user",
                "content": f"""Write a luxury product description for a jewellery piece called "{name}".
Category: {category or 'Jewellery'}
Material/details: {material or 'premium imitation metals and stones'}
Keywords: {keywords or 'elegant, exclusive, handcrafted'}

Write 2-3 sentences. Tone: premium, editorial, emotional. Focus on how it feels to wear it.
Do NOT use generic phrases like 'perfect for any occasion'. Be specific and evocative.
Return only the description, no extra text."""
            }]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'Content-Type':      'application/json',
                'anthropic-version': '2023-06-01',
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            text = result.get('content',[{}])[0].get('text','')
            return jsonify({'description': text.strip()})
    except Exception as e:
        return jsonify({'error': f'AI unavailable: {str(e)[:80]}'}), 500

# ── Admin: order invoice HTML (print-ready) ───────────────────────────────────
@app.route('/henosis-admin/orders/<oid>/invoice')
@admin_required
def admin_order_invoice(oid):
    order    = db.get_order_by_id(oid)
    if not order: return redirect(url_for('admin_orders'))
    settings = db.get_settings()
    return render_template('admin/invoice.html', order=order, settings=settings)

# ── Admin: notifications API ──────────────────────────────────────────────────
@app.route('/henosis-admin/api/notifications')
@admin_required
def admin_api_notifications():
    notifs = db.get_notifications(20)
    for n in notifs:
        n['read'] = db._bool(n.get('read', False))
    return jsonify({
        'notifications': notifs,
        'unread': db.count_unread_notifications()
    })

@app.route('/henosis-admin/api/stats')
@admin_required
def admin_api_stats():
    orders   = db.get_all_orders()
    products = db.get_all_products()
    pending  = sum(1 for o in orders if o.get('status')=='Pending')
    low      = int(db.get_settings().get('low_stock_alert','3'))
    low_stock= sum(1 for p in products if 0 < p['stock'] <= low)
    revenue_today = sum(
        float(o.get('total',0)) for o in orders
        if str(o.get('created_at',''))[:10] == datetime.now().strftime('%Y-%m-%d')
    )
    return jsonify({
        'pending_orders': pending,
        'low_stock': low_stock,
        'unread_notifications': db.count_unread_notifications(),
        'revenue_today': revenue_today,
    })

# ── Admin: Ads Manager ────────────────────────────────────────────────────────
@app.route('/henosis-admin/ads')
@admin_required
def admin_ads():
    return render_template('admin/ads.html', settings=db.get_settings(),
                           ads=db.get_all_ads())

@app.route('/henosis-admin/ads/save', methods=['POST'])
@admin_required
def admin_save_ad():
    aid = request.form.get('id','').strip()
    # Handle image upload for ad
    image_key = request.form.get('existing_image_key','')
    img_file  = request.files.get('ad_image')
    if img_file and img_file.filename and allowed_file(img_file.filename):
        raw, mime = read_upload(img_file)
        image_key = db.save_site_image(raw, mime)

    data = {
        'name':       request.form.get('name',''),
        'type':       request.form.get('type','banner'),
        'position':   request.form.get('position','top'),
        'image_key':  image_key,
        'link_url':   request.form.get('link_url',''),
        'link_text':  request.form.get('link_text',''),
        'bg_color':   request.form.get('bg_color','#1a1a1a'),
        'text_color': request.form.get('text_color','#faf8f4'),
        'content':    request.form.get('content',''),
        'active':     bool(request.form.get('active')),
        'sort_order': int(request.form.get('sort_order',0) or 0),
        'start_date': request.form.get('start_date',''),
        'end_date':   request.form.get('end_date',''),
    }
    if aid:
        db.update_ad(aid, data)
        flash('Ad updated','success')
    else:
        db.create_ad(data)
        flash('Ad created','success')
    db.log_activity('Ad Saved', data['name'])
    return redirect(url_for('admin_ads'))

@app.route('/henosis-admin/ads/toggle/<aid>', methods=['POST'])
@admin_required
def admin_toggle_ad(aid):
    db.toggle_ad(aid)
    return redirect(url_for('admin_ads'))

@app.route('/henosis-admin/ads/delete/<aid>', methods=['POST'])
@admin_required
def admin_delete_ad(aid):
    db.delete_ad(aid)
    flash('Ad deleted','success')
    return redirect(url_for('admin_ads'))

# ── Admin: Media Library ──────────────────────────────────────────────────────
@app.route('/henosis-admin/media')
@admin_required
def admin_media():
    return render_template('admin/media.html', settings=db.get_settings(),
                           media=db.get_all_media())

@app.route('/henosis-admin/media/upload', methods=['POST'])
@admin_required
def admin_media_upload():
    files   = request.files.getlist('files')
    usage   = request.form.get('usage','general')
    count   = 0
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            raw, mime = read_upload(f)
            name = secure_filename(f.filename)
            db.save_media(name, raw, mime, usage)
            count += 1
    # Apply site usage assignments
    assign = request.form.get('assign_to','')
    if assign and count == 1:
        # Get last uploaded key
        media = db.get_all_media()
        if media:
            key = media[0]['key']
            db.save_setting(assign, key)
    flash(f'{count} image(s) uploaded to media library','success')
    db.log_activity('Media Uploaded', f'{count} files')
    return redirect(url_for('admin_media'))

@app.route('/henosis-admin/media/assign', methods=['POST'])
@admin_required
def admin_media_assign():
    key    = request.form.get('key','')
    target = request.form.get('target','')
    if key and target:
        db.save_setting(target, key)
        db.log_activity('Media Assigned', f'{target} = {key}')
        flash(f'Image applied to {target.replace("_key","").replace("_"," ")}','success')
    return redirect(url_for('admin_media'))

@app.route('/henosis-admin/media/delete/<mid>', methods=['POST'])
@admin_required
def admin_media_delete(mid):
    db.delete_media(mid)
    flash('Image deleted','success')
    return redirect(url_for('admin_media'))

# ── Public: serve media library images ───────────────────────────────────────
@app.route('/mimg/<key>')
def serve_media_image(key):
    row = db.get_media_by_key(key)
    if not row: return '', 404
    import base64
    return Response(base64.b64decode(row['data']), mimetype=row['mime_type'],
                    headers={'Cache-Control':'public,max-age=31536000,immutable'})

# ── Public: serve ad image ────────────────────────────────────────────────────
@app.route('/api/ads/<position>')
def api_ads(position):
    ads = db.get_ads_for_position(position)
    return jsonify(ads)
