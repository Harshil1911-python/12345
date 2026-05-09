"""
db.py — Database abstraction layer
Uses PostgreSQL (via DATABASE_URL env var) on Render/Railway.
Falls back to SQLite locally for development.
"""
import os, sqlite3, uuid, json
from datetime import datetime

# ─── Connection ───────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

# Render gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith('postgresql'))

def get_conn():
    if USE_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        db_path = os.path.join(os.path.dirname(__file__), 'data', 'henosis.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

def placeholder():
    """Return the right placeholder for parameterised queries."""
    return '%s' if USE_POSTGRES else '?'

PH = placeholder()

# ─── Schema ───────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    price       REAL NOT NULL DEFAULT 0,
    description TEXT,
    category    TEXT,
    stock       INTEGER DEFAULT 1,
    only_one    BOOLEAN DEFAULT FALSE,
    images      TEXT DEFAULT '',
    featured    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    subtotal        REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    total           REAL DEFAULT 0,
    status          TEXT DEFAULT 'Pending',
    payment_status  TEXT DEFAULT 'Unpaid',
    note            TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    total_spent  REAL    DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS discounts (
    code          TEXT PRIMARY KEY,
    discount_type TEXT DEFAULT 'percent',
    value         REAL DEFAULT 10,
    min_order     REAL DEFAULT 0,
    uses_left     INTEGER DEFAULT 100,
    active        BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id            TEXT PRIMARY KEY,
    product_id    TEXT,
    customer_name TEXT,
    rating        INTEGER DEFAULT 5,
    comment       TEXT,
    approved      BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_SETTINGS = {
    'tagline':          'Crafted to stand alone.',
    'hero_text':        'Where rarity meets artistry. Each piece tells a story that belongs to one soul.',
    'banner_text':      'Free shipping on orders above ₹2000 · Exclusively crafted · One of a kind',
    'banner_active':    'true',
    'logo_text':        'HENOSIS',
    'logo_image':       '',
    'hero_image':       '',
    'primary_color':    '#b8965a',
    'accent_color':     '#c9a96e',
    'footer_text':      'Crafted with intention.',
    'about_title':      'Where rarity meets artistry',
    'about_body':       'Henosis was born from a belief that jewellery should be more than an accessory.',
    'contact_email':    'henosis4india@gmail.com',
    'contact_phone':    '',
    'instagram_url':    '',
    'pinterest_url':    '',
    'whatsapp_number':  '',
    'free_shipping_min':'2000',
    'currency_symbol':  '₹',
    'low_stock_alert':  '3',
    'maintenance_mode': 'false',
    'popup_enabled':    'false',
    'popup_title':      'Welcome to Henosis',
    'popup_text':       'Discover pieces crafted to stand alone.',
    'popup_cta':        'Shop Now',
    'meta_title':       'HENOSIS — Crafted to stand alone.',
    'meta_description': 'Luxury imitation jewellery. Exclusively crafted. One of a kind.',
    'show_reviews':     'true',
    'google_analytics': '',
    'whatsapp_chat':    'false',
}

def init_db():
    """Create all tables and seed default settings."""
    conn = get_conn()
    cur  = conn.cursor()
    if USE_POSTGRES:
        for stmt in SCHEMA.strip().split('\n\n'):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
    else:
        cur.executescript(SCHEMA)
    # Seed default settings
    for k, v in DEFAULT_SETTINGS.items():
        if USE_POSTGRES:
            cur.execute(
                "INSERT INTO settings (key,value) VALUES (%s,%s) ON CONFLICT(key) DO NOTHING",
                (k, v))
        else:
            cur.execute(
                "INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)",
                (k, v))
    conn.commit()
    conn.close()

# ─── Row → dict helper ────────────────────────────────────────────────────────
def row_to_dict(row):
    if row is None:
        return None
    if hasattr(row, '_asdict'):
        return dict(row._asdict())
    if hasattr(row, 'keys'):
        return dict(row)
    return dict(row)

def rows_to_dicts(rows):
    return [row_to_dict(r) for r in rows]

# ─── Settings ─────────────────────────────────────────────────────────────────
def get_settings():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall(); conn.close()
    return {r[0]: r[1] for r in rows}

def set_setting(key, value):
    conn = get_conn(); cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (key, value))
    else:
        cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
    conn.commit(); conn.close()

def set_settings_bulk(data: dict):
    conn = get_conn(); cur = conn.cursor()
    for k, v in data.items():
        if USE_POSTGRES:
            cur.execute("INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (k, v))
        else:
            cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, v))
    conn.commit(); conn.close()

# ─── Products ─────────────────────────────────────────────────────────────────
def get_all_products():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM products ORDER BY created_at DESC")
    rows = rows_to_dicts(cur.fetchall()); conn.close()
    for r in rows:
        r['only_one'] = str(r['only_one']).lower() in ('true','1','t')
        r['featured']  = str(r['featured']).lower() in ('true','1','t')
        r['only_one_str'] = 'true' if r['only_one'] else 'false'
        r['featured_str'] = 'true' if r['featured'] else 'false'
    return rows

def get_product_by_id(pid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM products WHERE id={PH}", (pid,))
    row = row_to_dict(cur.fetchone()); conn.close()
    if row:
        row['only_one'] = str(row['only_one']).lower() in ('true','1','t')
        row['featured']  = str(row['featured']).lower() in ('true','1','t')
        row['only_one_str'] = 'true' if row['only_one'] else 'false'
        row['featured_str'] = 'true' if row['featured'] else 'false'
    return row

def create_product(data):
    conn = get_conn(); cur = conn.cursor()
    pid = str(uuid.uuid4())[:8].upper()
    cur.execute(f"""INSERT INTO products (id,name,price,description,category,stock,only_one,images,featured,created_at)
        VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})""",
        (pid, data['name'], float(data.get('price',0)), data.get('description',''),
         data.get('category',''), int(data.get('stock',1)),
         data.get('only_one',False), data.get('images',''),
         data.get('featured',False), datetime.now()))
    conn.commit(); conn.close(); return pid

def update_product(pid, data):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"""UPDATE products SET name={PH},price={PH},description={PH},category={PH},
        stock={PH},only_one={PH},images={PH},featured={PH} WHERE id={PH}""",
        (data['name'], float(data.get('price',0)), data.get('description',''),
         data.get('category',''), int(data.get('stock',1)),
         data.get('only_one',False), data.get('images',''),
         data.get('featured',False), pid))
    conn.commit(); conn.close()

def delete_product(pid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM products WHERE id={PH}", (pid,))
    conn.commit(); conn.close()

def decrement_stock(pid, qty, only_one):
    conn = get_conn(); cur = conn.cursor()
    if only_one:
        cur.execute(f"UPDATE products SET stock=0 WHERE id={PH}", (pid,))
    else:
        cur.execute(f"UPDATE products SET stock=GREATEST(0,stock-{PH}) WHERE id={PH}" if USE_POSTGRES
                    else f"UPDATE products SET stock=MAX(0,stock-{PH}) WHERE id={PH}", (qty, pid))
    conn.commit(); conn.close()

# ─── Orders ───────────────────────────────────────────────────────────────────
def get_all_orders(status_filter=None):
    conn = get_conn(); cur = conn.cursor()
    if status_filter:
        cur.execute(f"SELECT * FROM orders WHERE status={PH} ORDER BY created_at DESC", (status_filter,))
    else:
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = rows_to_dicts(cur.fetchall()); conn.close()
    return rows

def get_order_by_id(oid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM orders WHERE id={PH}", (oid,))
    return row_to_dict(cur.fetchone())

def create_order(data):
    conn = get_conn(); cur = conn.cursor()
    oid = str(uuid.uuid4())[:8].upper()
    cur.execute(f"""INSERT INTO orders
        (id,customer_name,email,phone,address,city,pincode,items,subtotal,discount_amount,total,status,payment_status,note,created_at)
        VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})""",
        (oid, data['customer_name'], data['email'], data['phone'],
         data['address'], data['city'], data['pincode'], data['items'],
         data.get('subtotal',0), data.get('discount_amount',0), data['total'],
         'Pending','Unpaid', data.get('note',''), datetime.now()))
    conn.commit(); conn.close(); return oid

def update_order(oid, status, payment_status, note=''):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"UPDATE orders SET status={PH},payment_status={PH},note={PH} WHERE id={PH}",
                (status, payment_status, note, oid))
    conn.commit(); conn.close()

def delete_order(oid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM orders WHERE id={PH}", (oid,))
    conn.commit(); conn.close()

# ─── Customers ────────────────────────────────────────────────────────────────
def get_all_customers():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM customers ORDER BY created_at DESC")
    return rows_to_dicts(cur.fetchall())

def upsert_customer(data, order_total):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"SELECT id FROM customers WHERE email={PH}", (data.get('email',''),))
    existing = cur.fetchone()
    if existing:
        cur.execute(f"UPDATE customers SET total_orders=total_orders+1, total_spent=total_spent+{PH}, phone={PH} WHERE email={PH}",
                    (float(order_total), data.get('phone',''), data.get('email','')))
    else:
        cur.execute(f"""INSERT INTO customers (id,name,email,phone,address,city,pincode,total_orders,total_spent,created_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},1,{PH},{PH})""",
            (str(uuid.uuid4())[:8].upper(), data.get('name',''), data.get('email',''),
             data.get('phone',''), data.get('address',''), data.get('city',''),
             data.get('pincode',''), float(order_total), datetime.now()))
    conn.commit(); conn.close()

def delete_customer(cid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM customers WHERE id={PH}", (cid,))
    conn.commit(); conn.close()

# ─── Discounts ────────────────────────────────────────────────────────────────
def get_all_discounts():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM discounts ORDER BY created_at DESC")
    return rows_to_dicts(cur.fetchall())

def get_discount(code):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM discounts WHERE UPPER(code)=UPPER({PH})", (code,))
    return row_to_dict(cur.fetchone())

def create_discount(data):
    conn = get_conn(); cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("""INSERT INTO discounts(code,discount_type,value,min_order,uses_left,active,created_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(code) DO NOTHING""",
            (data['code'].upper(), data['discount_type'], float(data['value']),
             float(data.get('min_order',0)), int(data.get('uses_left',100)),
             True, datetime.now()))
    else:
        cur.execute("""INSERT OR IGNORE INTO discounts(code,discount_type,value,min_order,uses_left,active,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (data['code'].upper(), data['discount_type'], float(data['value']),
             float(data.get('min_order',0)), int(data.get('uses_left',100)),
             1, datetime.now()))
    conn.commit(); conn.close()

def toggle_discount(code):
    conn = get_conn(); cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("UPDATE discounts SET active = NOT active WHERE UPPER(code)=UPPER(%s)", (code,))
    else:
        cur.execute("UPDATE discounts SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE UPPER(code)=UPPER(?)", (code,))
    conn.commit(); conn.close()

def decrement_discount(code):
    conn = get_conn(); cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("UPDATE discounts SET uses_left=GREATEST(0,uses_left-1) WHERE UPPER(code)=UPPER(%s)", (code,))
    else:
        cur.execute("UPDATE discounts SET uses_left=MAX(0,uses_left-1) WHERE UPPER(code)=UPPER(?)", (code,))
    conn.commit(); conn.close()

def delete_discount(code):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM discounts WHERE UPPER(code)=UPPER({PH})", (code,))
    conn.commit(); conn.close()

# ─── Reviews ──────────────────────────────────────────────────────────────────
def get_all_reviews():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM reviews ORDER BY created_at DESC")
    rows = rows_to_dicts(cur.fetchall()); conn.close()
    for r in rows:
        r['approved'] = str(r['approved']).lower() in ('true','1','t')
        r['approved_str'] = 'true' if r['approved'] else 'false'
    return rows

def get_reviews_for_product(pid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM reviews WHERE product_id={PH} AND approved=TRUE ORDER BY created_at DESC"
                if USE_POSTGRES else
                f"SELECT * FROM reviews WHERE product_id={PH} AND approved=1 ORDER BY created_at DESC", (pid,))
    rows = rows_to_dicts(cur.fetchall()); conn.close()
    return rows

def create_review(data):
    conn = get_conn(); cur = conn.cursor()
    rid = str(uuid.uuid4())[:8].upper()
    cur.execute(f"""INSERT INTO reviews(id,product_id,customer_name,rating,comment,approved,created_at)
        VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH})""",
        (rid, data['product_id'], data['customer_name'],
         int(data.get('rating',5)), data['comment'],
         False, datetime.now()))
    conn.commit(); conn.close()

def approve_review(rid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"UPDATE reviews SET approved=TRUE WHERE id={PH}" if USE_POSTGRES
                else f"UPDATE reviews SET approved=1 WHERE id={PH}", (rid,))
    conn.commit(); conn.close()

def delete_review(rid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM reviews WHERE id={PH}", (rid,))
    conn.commit(); conn.close()

# ─── Analytics helpers ────────────────────────────────────────────────────────
def get_revenue_by_day(days=7):
    from collections import defaultdict
    orders = get_all_orders()
    daily  = defaultdict(float)
    for o in orders:
        day = str(o.get('created_at',''))[:10]
        daily[day] += float(o.get('total',0))
    return sorted(daily.items())[-days:]

def get_top_products(limit=5):
    orders   = get_all_orders()
    products = get_all_products()
    prod_map = {p['id']: p['name'] for p in products}
    counts   = {}
    for o in orders:
        for item in str(o.get('items','')).split(' | '):
            pid = item.split(' ')[0] if item else ''
            for p in products:
                if p['name'] in item:
                    counts[p['id']] = counts.get(p['id'],0) + 1
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
