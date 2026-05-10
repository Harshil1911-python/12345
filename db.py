"""
db.py  —  Pure PostgreSQL database layer for Henosis
All images stored as base64 TEXT inside PostgreSQL.
No CSV, no DAT, no filesystem dependency.
Falls back to SQLite for local dev (same API).
"""
import os, sqlite3, uuid, base64, io
from datetime import datetime

# ── Connection ────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

USE_PG = bool(DATABASE_URL and DATABASE_URL.startswith('postgresql'))
PH     = '%s' if USE_PG else '?'

def get_conn():
    if USE_PG:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    path = os.path.join(os.path.dirname(__file__), 'data', 'henosis.db')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def _exec(sql, params=(), fetch='none', commit=False):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(sql, params)
    result = None
    if fetch == 'one':  result = _row(cur.fetchone())
    if fetch == 'all':  result = [_row(r) for r in cur.fetchall()]
    if commit: conn.commit()
    conn.close()
    return result

def _row(row):
    if row is None: return None
    return dict(row) if not hasattr(row,'keys') else dict(zip(row.keys(), tuple(row)))

def _bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, int):  return v != 0
    return str(v).lower() in ('true','1','t','yes')

# ── Schema ────────────────────────────────────────────────────────────────────
_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS products (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    price       NUMERIC(10,2) NOT NULL DEFAULT 0,
    description TEXT,
    category    TEXT,
    stock       INTEGER DEFAULT 1,
    only_one    BOOLEAN DEFAULT FALSE,
    featured    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS product_images (
    id          TEXT PRIMARY KEY,
    product_id  TEXT REFERENCES products(id) ON DELETE CASCADE,
    data        TEXT NOT NULL,
    mime_type   TEXT DEFAULT 'image/jpeg',
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    customer_name   TEXT,
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    city            TEXT,
    pincode         TEXT,
    items           TEXT,
    subtotal        NUMERIC(10,2) DEFAULT 0,
    discount_code   TEXT DEFAULT '',
    discount_amount NUMERIC(10,2) DEFAULT 0,
    total           NUMERIC(10,2) DEFAULT 0,
    status          TEXT DEFAULT 'Pending',
    payment_status  TEXT DEFAULT 'Unpaid',
    note            TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS customers (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    email        TEXT UNIQUE,
    phone        TEXT,
    address      TEXT,
    city         TEXT,
    pincode      TEXT,
    total_orders INTEGER DEFAULT 0,
    total_spent  NUMERIC(10,2) DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS discounts (
    code          TEXT PRIMARY KEY,
    discount_type TEXT DEFAULT 'percent',
    value         NUMERIC(10,2) DEFAULT 10,
    min_order     NUMERIC(10,2) DEFAULT 0,
    uses_left     INTEGER DEFAULT 100,
    active        BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS reviews (
    id            TEXT PRIMARY KEY,
    product_id    TEXT,
    customer_name TEXT,
    rating        INTEGER DEFAULT 5,
    comment       TEXT,
    approved      BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS site_images (
    key        TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    mime_type  TEXT DEFAULT 'image/jpeg',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_SCHEMA_SQ = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, price REAL DEFAULT 0,
    description TEXT, category TEXT, stock INTEGER DEFAULT 1,
    only_one INTEGER DEFAULT 0, featured INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS product_images (
    id TEXT PRIMARY KEY, product_id TEXT, data TEXT NOT NULL,
    mime_type TEXT DEFAULT 'image/jpeg', sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, customer_name TEXT, email TEXT, phone TEXT,
    address TEXT, city TEXT, pincode TEXT, items TEXT,
    subtotal REAL DEFAULT 0, discount_code TEXT DEFAULT '',
    discount_amount REAL DEFAULT 0, total REAL DEFAULT 0,
    status TEXT DEFAULT 'Pending', payment_status TEXT DEFAULT 'Unpaid',
    note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY, name TEXT, email TEXT UNIQUE, phone TEXT,
    address TEXT, city TEXT, pincode TEXT,
    total_orders INTEGER DEFAULT 0, total_spent REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS discounts (
    code TEXT PRIMARY KEY, discount_type TEXT DEFAULT 'percent',
    value REAL DEFAULT 10, min_order REAL DEFAULT 0,
    uses_left INTEGER DEFAULT 100, active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY, product_id TEXT, customer_name TEXT,
    rating INTEGER DEFAULT 5, comment TEXT, approved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS site_images (
    key TEXT PRIMARY KEY, data TEXT NOT NULL,
    mime_type TEXT DEFAULT 'image/jpeg',
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_DEFAULTS = {
    'tagline':'Crafted to stand alone.',
    'hero_text':'Where rarity meets artistry. Each piece tells a story that belongs to one soul.',
    'banner_text':'Free shipping on orders above ₹2000 · Exclusively crafted · One of a kind',
    'banner_active':'true',
    'logo_text':'HENOSIS',
    'logo_image_key':'',
    'hero_image_key':'',
    'primary_color':'#b8965a',
    'accent_color':'#c9a96e',
    'footer_text':'Crafted with intention.',
    'about_title':'Where rarity meets artistry',
    'about_body':'Henosis was born from a belief that jewellery should be more than an accessory.',
    'contact_email':'henosis4india@gmail.com',
    'contact_phone':'',
    'instagram_url':'',
    'pinterest_url':'',
    'whatsapp_number':'',
    'whatsapp_chat':'false',
    'free_shipping_min':'2000',
    'currency_symbol':'₹',
    'low_stock_alert':'3',
    'maintenance_mode':'false',
    'popup_enabled':'false',
    'popup_title':'Welcome to Henosis',
    'popup_text':'Discover pieces crafted to stand alone.',
    'popup_cta':'Shop Now',
    'meta_title':'HENOSIS — Crafted to stand alone.',
    'meta_description':'Luxury imitation jewellery. Exclusively crafted. One of a kind.',
    'show_reviews':'true',
    'google_analytics':'',
}

def init_db():
    conn = get_conn(); cur = conn.cursor()
    if USE_PG:
        for stmt in _SCHEMA_PG.strip().split('\n\n'):
            s = stmt.strip()
            if s: cur.execute(s)
        for k, v in _DEFAULTS.items():
            cur.execute("INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO NOTHING", (k,v))
    else:
        conn.executescript(_SCHEMA_SQ)
        for k, v in _DEFAULTS.items():
            cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k,v))
    conn.commit(); conn.close()

# ── Image helpers ─────────────────────────────────────────────────────────────
def _compress_image(file_bytes, mime_type, max_px=1200, quality=82):
    """Compress image and return base64 string. Works without Pillow too."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        img = img.convert('RGB')
        w, h = img.size
        if max(w,h) > max_px:
            ratio = max_px / max(w,h)
            img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode(), 'image/jpeg'
    except Exception:
        return base64.b64encode(file_bytes).decode(), mime_type

def save_image_to_db(file_bytes, mime_type, max_px=1200, quality=82):
    """Store image in DB, return image id."""
    b64, final_mime = _compress_image(file_bytes, mime_type, max_px, quality)
    img_id = str(uuid.uuid4())
    _exec(f"INSERT INTO site_images(key,data,mime_type) VALUES({PH},{PH},{PH})",
          (img_id, b64, final_mime), commit=True)
    return img_id

def save_product_image(product_id, file_bytes, mime_type, sort_order=0):
    """Store product image in DB, return image id."""
    b64, final_mime = _compress_image(file_bytes, mime_type)
    img_id = str(uuid.uuid4())
    _exec(f"INSERT INTO product_images(id,product_id,data,mime_type,sort_order) VALUES({PH},{PH},{PH},{PH},{PH})",
          (img_id, product_id, b64, final_mime, sort_order), commit=True)
    return img_id

def get_image_data(key):
    """Return (base64_data, mime_type) or (None, None)."""
    row = _exec(f"SELECT data, mime_type FROM site_images WHERE key={PH}", (key,), fetch='one')
    if row: return row['data'], row['mime_type']
    return None, None

def get_product_images(product_id):
    """Return list of {id, data, mime_type} sorted by sort_order."""
    return _exec(f"SELECT id, data, mime_type FROM product_images WHERE product_id={PH} ORDER BY sort_order",
                 (product_id,), fetch='all') or []

def delete_product_image(img_id):
    _exec(f"DELETE FROM product_images WHERE id={PH}", (img_id,), commit=True)

def delete_all_product_images(product_id):
    _exec(f"DELETE FROM product_images WHERE product_id={PH}", (product_id,), commit=True)

# ── Settings ─────────────────────────────────────────────────────────────────
def get_settings():
    rows = _exec("SELECT key,value FROM settings", fetch='all') or []
    return {r['key']:r['value'] for r in rows}

def set_setting(key, value):
    if USE_PG:
        _exec("INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
              (key, value), commit=True)
    else:
        _exec("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value), commit=True)

def set_settings_bulk(data):
    conn = get_conn(); cur = conn.cursor()
    for k, v in data.items():
        if USE_PG:
            cur.execute("INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (k,v))
        else:
            cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k,v))
    conn.commit(); conn.close()

# ── Products ─────────────────────────────────────────────────────────────────
def _norm_product(p):
    if not p: return None
    p['only_one']     = _bool(p.get('only_one', False))
    p['featured']     = _bool(p.get('featured', False))
    p['only_one_str'] = 'true' if p['only_one'] else 'false'
    p['featured_str'] = 'true' if p['featured'] else 'false'
    p['price']        = float(p.get('price', 0))
    p['stock']        = int(p.get('stock', 0))
    return p

def get_all_products():
    rows = _exec("SELECT * FROM products ORDER BY created_at DESC", fetch='all') or []
    return [_norm_product(r) for r in rows]

def get_product_by_id(pid):
    return _norm_product(_exec(f"SELECT * FROM products WHERE id={PH}", (pid,), fetch='one'))

def create_product(data):
    pid = str(uuid.uuid4())[:8].upper()
    _exec(f"INSERT INTO products(id,name,price,description,category,stock,only_one,featured,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})",
          (pid, data['name'], float(data.get('price',0)), data.get('description',''),
           data.get('category',''), int(data.get('stock',1)),
           bool(data.get('only_one',False)), bool(data.get('featured',False)),
           datetime.now()), commit=True)
    return pid

def update_product(pid, data):
    _exec(f"UPDATE products SET name={PH},price={PH},description={PH},category={PH},stock={PH},only_one={PH},featured={PH} WHERE id={PH}",
          (data['name'], float(data.get('price',0)), data.get('description',''),
           data.get('category',''), int(data.get('stock',1)),
           bool(data.get('only_one',False)), bool(data.get('featured',False)), pid), commit=True)

def delete_product(pid):
    _exec(f"DELETE FROM products WHERE id={PH}", (pid,), commit=True)

def decrement_stock(pid, qty, only_one):
    if only_one:
        _exec(f"UPDATE products SET stock=0 WHERE id={PH}", (pid,), commit=True)
    elif USE_PG:
        _exec(f"UPDATE products SET stock=GREATEST(0,stock-{PH}) WHERE id={PH}", (qty,pid), commit=True)
    else:
        _exec(f"UPDATE products SET stock=MAX(0,stock-{PH}) WHERE id={PH}", (qty,pid), commit=True)

# ── Orders ────────────────────────────────────────────────────────────────────
def get_all_orders(status_filter=None):
    if status_filter:
        return _exec(f"SELECT * FROM orders WHERE status={PH} ORDER BY created_at DESC", (status_filter,), fetch='all') or []
    return _exec("SELECT * FROM orders ORDER BY created_at DESC", fetch='all') or []

def get_order_by_id(oid):
    return _exec(f"SELECT * FROM orders WHERE id={PH}", (oid,), fetch='one')

def create_order(data):
    oid = str(uuid.uuid4())[:8].upper()
    _exec(f"INSERT INTO orders(id,customer_name,email,phone,address,city,pincode,items,subtotal,discount_code,discount_amount,total,status,payment_status,note,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})",
          (oid, data['customer_name'], data['email'], data['phone'],
           data['address'], data['city'], data['pincode'], data['items'],
           data.get('subtotal',0), data.get('discount_code',''),
           data.get('discount_amount',0), data['total'],
           'Pending','Unpaid', data.get('note',''), datetime.now()), commit=True)
    return oid

def update_order(oid, status, payment_status, note=''):
    _exec(f"UPDATE orders SET status={PH},payment_status={PH},note={PH} WHERE id={PH}",
          (status, payment_status, note, oid), commit=True)

def delete_order(oid):
    _exec(f"DELETE FROM orders WHERE id={PH}", (oid,), commit=True)

# ── Customers ─────────────────────────────────────────────────────────────────
def get_all_customers():
    return _exec("SELECT * FROM customers ORDER BY created_at DESC", fetch='all') or []

def upsert_customer(data, order_total):
    email = data.get('email','')
    existing = _exec(f"SELECT id FROM customers WHERE email={PH}", (email,), fetch='one')
    if existing:
        _exec(f"UPDATE customers SET total_orders=total_orders+1, total_spent=total_spent+{PH}, phone={PH} WHERE email={PH}",
              (float(order_total), data.get('phone',''), email), commit=True)
    else:
        _exec(f"INSERT INTO customers(id,name,email,phone,address,city,pincode,total_orders,total_spent,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH},1,{PH},{PH})",
              (str(uuid.uuid4())[:8].upper(), data.get('name',''), email,
               data.get('phone',''), data.get('address',''), data.get('city',''),
               data.get('pincode',''), float(order_total), datetime.now()), commit=True)

def delete_customer(cid):
    _exec(f"DELETE FROM customers WHERE id={PH}", (cid,), commit=True)

# ── Discounts ─────────────────────────────────────────────────────────────────
def _norm_discount(d):
    if not d: return None
    d['active']     = _bool(d.get('active', True))
    d['active_str'] = 'true' if d['active'] else 'false'
    d['value']      = float(d.get('value', 0))
    d['min_order']  = float(d.get('min_order', 0))
    d['uses_left']  = int(d.get('uses_left', 0))
    return d

def get_all_discounts():
    rows = _exec("SELECT * FROM discounts ORDER BY created_at DESC", fetch='all') or []
    return [_norm_discount(r) for r in rows]

def get_discount(code):
    return _norm_discount(_exec(f"SELECT * FROM discounts WHERE UPPER(code)=UPPER({PH})", (code,), fetch='one'))

def create_discount(data):
    code = data['code'].upper()
    if USE_PG:
        _exec("INSERT INTO discounts(code,discount_type,value,min_order,uses_left,active,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(code) DO NOTHING",
              (code, data['discount_type'], float(data['value']),
               float(data.get('min_order',0)), int(data.get('uses_left',100)),
               True, datetime.now()), commit=True)
    else:
        _exec("INSERT OR IGNORE INTO discounts(code,discount_type,value,min_order,uses_left,active,created_at) VALUES(?,?,?,?,?,?,?)",
              (code, data['discount_type'], float(data['value']),
               float(data.get('min_order',0)), int(data.get('uses_left',100)),
               1, datetime.now()), commit=True)

def toggle_discount(code):
    if USE_PG:
        _exec("UPDATE discounts SET active = NOT active WHERE UPPER(code)=UPPER(%s)", (code,), commit=True)
    else:
        _exec("UPDATE discounts SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE UPPER(code)=UPPER(?)", (code,), commit=True)

def decrement_discount(code):
    if USE_PG:
        _exec("UPDATE discounts SET uses_left=GREATEST(0,uses_left-1) WHERE UPPER(code)=UPPER(%s)", (code,), commit=True)
    else:
        _exec("UPDATE discounts SET uses_left=MAX(0,uses_left-1) WHERE UPPER(code)=UPPER(?)", (code,), commit=True)

def delete_discount(code):
    _exec(f"DELETE FROM discounts WHERE UPPER(code)=UPPER({PH})", (code,), commit=True)

# ── Reviews ───────────────────────────────────────────────────────────────────
def _norm_review(r):
    if not r: return None
    r['approved']     = _bool(r.get('approved', False))
    r['approved_str'] = 'true' if r['approved'] else 'false'
    r['rating']       = int(r.get('rating', 5))
    return r

def get_all_reviews():
    rows = _exec("SELECT * FROM reviews ORDER BY created_at DESC", fetch='all') or []
    return [_norm_review(r) for r in rows]

def get_reviews_for_product(pid):
    if USE_PG:
        rows = _exec(f"SELECT * FROM reviews WHERE product_id={PH} AND approved=TRUE ORDER BY created_at DESC", (pid,), fetch='all') or []
    else:
        rows = _exec(f"SELECT * FROM reviews WHERE product_id={PH} AND approved=1 ORDER BY created_at DESC", (pid,), fetch='all') or []
    return [_norm_review(r) for r in rows]

def create_review(data):
    rid = str(uuid.uuid4())[:8].upper()
    _exec(f"INSERT INTO reviews(id,product_id,customer_name,rating,comment,approved,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH})",
          (rid, data['product_id'], data['customer_name'],
           int(data.get('rating',5)), data['comment'],
           False, datetime.now()), commit=True)

def approve_review(rid):
    val = True if USE_PG else 1
    _exec(f"UPDATE reviews SET approved={PH} WHERE id={PH}", (val, rid), commit=True)

def delete_review(rid):
    _exec(f"DELETE FROM reviews WHERE id={PH}", (rid,), commit=True)

# ── Analytics ─────────────────────────────────────────────────────────────────
def get_revenue_by_day(days=7):
    from collections import defaultdict
    orders = get_all_orders()
    daily  = defaultdict(float)
    for o in orders:
        day = str(o.get('created_at',''))[:10]
        daily[day] += float(o.get('total', 0))
    return sorted(daily.items())[-days:]
