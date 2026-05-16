"""
db.py — Henosis Production Database Layer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PostgreSQL  →  when DATABASE_URL env var is set  (Render / any cloud host)
SQLite      →  automatic fallback for local dev   (zero config needed)

KEY DESIGN RULES:
  • init_db() only creates tables + adds MISSING settings — NEVER overwrites
  • save_setting() / save_settings_bulk() only touch keys you explicitly pass
  • Images stored as base64 TEXT inside DB — no filesystem, no Cloudinary needed
  • Thread-safe: each call opens+closes its own connection
  • Migration-safe: ALTER TABLE IF NOT EXISTS for every new column
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os, sqlite3, uuid, base64, io
from datetime import datetime

# ─── Connection ───────────────────────────────────────────────────────────────
_RAW = os.environ.get('DATABASE_URL', '')
DATABASE_URL = _RAW.replace('postgres://', 'postgresql://', 1) \
               if _RAW.startswith('postgres://') else _RAW
USE_PG = DATABASE_URL.startswith('postgresql')
PH     = '%s' if USE_PG else '?'

def get_conn():
    if USE_PG:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'henosis.db')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def _exec(sql, params=(), fetch='none', commit=False):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(sql, params)
    result = None
    if   fetch == 'one': result = _row(cur.fetchone())
    elif fetch == 'all': result = [_row(r) for r in cur.fetchall()]
    if commit: conn.commit()
    conn.close()
    return result

def _row(r):
    if r is None: return None
    if hasattr(r, 'keys'):
        d = dict(zip(r.keys(), tuple(r)))
    else:
        d = dict(r)
    return d

def _bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, int):  return v != 0
    return str(v).lower() in ('true','1','t','yes')

# ─── Schema ────────────────────────────────────────────────────────────────────
# Each table listed separately so migration is easy to extend
_PG_TABLES = [
"CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT DEFAULT '')",
"""CREATE TABLE IF NOT EXISTS products(
    id TEXT PRIMARY KEY, name TEXT NOT NULL, price NUMERIC(12,2) DEFAULT 0,
    description TEXT DEFAULT '', category TEXT DEFAULT '',
    stock INTEGER DEFAULT 1, only_one BOOLEAN DEFAULT FALSE,
    featured BOOLEAN DEFAULT FALSE, sort_order INTEGER DEFAULT 0,
    material TEXT DEFAULT '', dimensions TEXT DEFAULT '',
    care_instructions TEXT DEFAULT '', meta_title TEXT DEFAULT '',
    meta_description TEXT DEFAULT '', publish_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW())""",
"""CREATE TABLE IF NOT EXISTS product_images(
    id TEXT PRIMARY KEY, product_id TEXT REFERENCES products(id) ON DELETE CASCADE,
    data TEXT NOT NULL, mime_type TEXT DEFAULT 'image/jpeg',
    sort_order INTEGER DEFAULT 0, created_at TIMESTAMPTZ DEFAULT NOW())""",
"""CREATE TABLE IF NOT EXISTS orders(
    id TEXT PRIMARY KEY, customer_name TEXT DEFAULT '', email TEXT DEFAULT '',
    phone TEXT DEFAULT '', address TEXT DEFAULT '', city TEXT DEFAULT '',
    pincode TEXT DEFAULT '', items TEXT DEFAULT '',
    subtotal NUMERIC(12,2) DEFAULT 0, discount_code TEXT DEFAULT '',
    discount_amount NUMERIC(12,2) DEFAULT 0, total NUMERIC(12,2) DEFAULT 0,
    status TEXT DEFAULT 'Pending', payment_status TEXT DEFAULT 'Unpaid',
    note TEXT DEFAULT '', admin_note TEXT DEFAULT '',
    tracking_number TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())""",
"""CREATE TABLE IF NOT EXISTS order_timeline(
    id TEXT PRIMARY KEY, order_id TEXT REFERENCES orders(id) ON DELETE CASCADE,
    event TEXT DEFAULT '', note TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW())""",
"""CREATE TABLE IF NOT EXISTS customers(
    id TEXT PRIMARY KEY, name TEXT DEFAULT '', email TEXT UNIQUE,
    phone TEXT DEFAULT '', address TEXT DEFAULT '', city TEXT DEFAULT '',
    pincode TEXT DEFAULT '', total_orders INTEGER DEFAULT 0,
    total_spent NUMERIC(12,2) DEFAULT 0, tags TEXT DEFAULT '',
    private_note TEXT DEFAULT '', blocked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW())""",
"""CREATE TABLE IF NOT EXISTS discounts(
    code TEXT PRIMARY KEY, discount_type TEXT DEFAULT 'percent',
    value NUMERIC(10,2) DEFAULT 10, min_order NUMERIC(10,2) DEFAULT 0,
    uses_left INTEGER DEFAULT 100, active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW())""",
"""CREATE TABLE IF NOT EXISTS reviews(
    id TEXT PRIMARY KEY, product_id TEXT DEFAULT '',
    customer_name TEXT DEFAULT '', rating INTEGER DEFAULT 5,
    comment TEXT DEFAULT '', approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW())""",
"CREATE TABLE IF NOT EXISTS site_images(key TEXT PRIMARY KEY, data TEXT NOT NULL, mime_type TEXT DEFAULT 'image/jpeg', updated_at TIMESTAMPTZ DEFAULT NOW())",
"CREATE TABLE IF NOT EXISTS activity_log(id TEXT PRIMARY KEY, action TEXT DEFAULT '', detail TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())",
"CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY, type TEXT DEFAULT 'info', title TEXT DEFAULT '', body TEXT DEFAULT '', read BOOLEAN DEFAULT FALSE, link TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())",
"""CREATE TABLE IF NOT EXISTS pages(
    id TEXT PRIMARY KEY, title TEXT DEFAULT '', slug TEXT UNIQUE,
    content TEXT DEFAULT '', published BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW())""",
"CREATE TABLE IF NOT EXISTS expenses(id TEXT PRIMARY KEY, description TEXT DEFAULT '', amount NUMERIC(12,2) DEFAULT 0, category TEXT DEFAULT 'Other', expense_date TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())",
"CREATE TABLE IF NOT EXISTS product_views(id TEXT PRIMARY KEY, product_id TEXT DEFAULT '', viewed_at TIMESTAMPTZ DEFAULT NOW())",
"CREATE TABLE IF NOT EXISTS notify_restock(id TEXT PRIMARY KEY, product_id TEXT DEFAULT '', email TEXT DEFAULT '', notified BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT NOW())",
"""CREATE TABLE IF NOT EXISTS ads(
    id TEXT PRIMARY KEY, name TEXT DEFAULT '', type TEXT DEFAULT 'banner',
    position TEXT DEFAULT 'top', image_key TEXT DEFAULT '',
    link_url TEXT DEFAULT '', link_text TEXT DEFAULT '',
    bg_color TEXT DEFAULT '#1a1a1a', text_color TEXT DEFAULT '#faf8f4',
    content TEXT DEFAULT '', active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0, start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())""",
"""CREATE TABLE IF NOT EXISTS media_library(
    id TEXT PRIMARY KEY, name TEXT DEFAULT '', key TEXT UNIQUE,
    data TEXT NOT NULL, mime_type TEXT DEFAULT 'image/jpeg',
    usage TEXT DEFAULT '', width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW())""",
]

_SQ_SCRIPT = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,name TEXT NOT NULL,price REAL DEFAULT 0,description TEXT DEFAULT '',category TEXT DEFAULT '',stock INTEGER DEFAULT 1,only_one INTEGER DEFAULT 0,featured INTEGER DEFAULT 0,sort_order INTEGER DEFAULT 0,material TEXT DEFAULT '',dimensions TEXT DEFAULT '',care_instructions TEXT DEFAULT '',meta_title TEXT DEFAULT '',meta_description TEXT DEFAULT '',publish_at TEXT DEFAULT(datetime('now')),created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS product_images(id TEXT PRIMARY KEY,product_id TEXT,data TEXT NOT NULL,mime_type TEXT DEFAULT 'image/jpeg',sort_order INTEGER DEFAULT 0,created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,customer_name TEXT DEFAULT '',email TEXT DEFAULT '',phone TEXT DEFAULT '',address TEXT DEFAULT '',city TEXT DEFAULT '',pincode TEXT DEFAULT '',items TEXT DEFAULT '',subtotal REAL DEFAULT 0,discount_code TEXT DEFAULT '',discount_amount REAL DEFAULT 0,total REAL DEFAULT 0,status TEXT DEFAULT 'Pending',payment_status TEXT DEFAULT 'Unpaid',note TEXT DEFAULT '',admin_note TEXT DEFAULT '',tracking_number TEXT DEFAULT '',created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS order_timeline(id TEXT PRIMARY KEY,order_id TEXT,event TEXT DEFAULT '',note TEXT DEFAULT '',created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY,name TEXT DEFAULT '',email TEXT UNIQUE,phone TEXT DEFAULT '',address TEXT DEFAULT '',city TEXT DEFAULT '',pincode TEXT DEFAULT '',total_orders INTEGER DEFAULT 0,total_spent REAL DEFAULT 0,tags TEXT DEFAULT '',private_note TEXT DEFAULT '',blocked INTEGER DEFAULT 0,created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS discounts(code TEXT PRIMARY KEY,discount_type TEXT DEFAULT 'percent',value REAL DEFAULT 10,min_order REAL DEFAULT 0,uses_left INTEGER DEFAULT 100,active INTEGER DEFAULT 1,created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,product_id TEXT DEFAULT '',customer_name TEXT DEFAULT '',rating INTEGER DEFAULT 5,comment TEXT DEFAULT '',approved INTEGER DEFAULT 0,created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS site_images(key TEXT PRIMARY KEY,data TEXT NOT NULL,mime_type TEXT DEFAULT 'image/jpeg',updated_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS activity_log(id TEXT PRIMARY KEY,action TEXT DEFAULT '',detail TEXT DEFAULT '',created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,type TEXT DEFAULT 'info',title TEXT DEFAULT '',body TEXT DEFAULT '',read INTEGER DEFAULT 0,link TEXT DEFAULT '',created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY,title TEXT DEFAULT '',slug TEXT UNIQUE,content TEXT DEFAULT '',published INTEGER DEFAULT 1,created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS expenses(id TEXT PRIMARY KEY,description TEXT DEFAULT '',amount REAL DEFAULT 0,category TEXT DEFAULT 'Other',expense_date TEXT DEFAULT '',created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS product_views(id TEXT PRIMARY KEY,product_id TEXT DEFAULT '',viewed_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS notify_restock(id TEXT PRIMARY KEY,product_id TEXT DEFAULT '',email TEXT DEFAULT '',notified INTEGER DEFAULT 0,created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS ads(id TEXT PRIMARY KEY,name TEXT DEFAULT '',type TEXT DEFAULT 'banner',position TEXT DEFAULT 'top',image_key TEXT DEFAULT '',link_url TEXT DEFAULT '',link_text TEXT DEFAULT '',bg_color TEXT DEFAULT '#1a1a1a',text_color TEXT DEFAULT '#faf8f4',content TEXT DEFAULT '',active INTEGER DEFAULT 1,sort_order INTEGER DEFAULT 0,start_date TEXT DEFAULT '',end_date TEXT DEFAULT '',created_at TEXT DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS media_library(id TEXT PRIMARY KEY,name TEXT DEFAULT '',key TEXT UNIQUE,data TEXT NOT NULL,mime_type TEXT DEFAULT 'image/jpeg',usage TEXT DEFAULT '',width INTEGER DEFAULT 0,height INTEGER DEFAULT 0,created_at TEXT DEFAULT(datetime('now')));
"""

# SQLite only — ALTER TABLE for new columns added after initial deploy
_SQ_MIGRATIONS = [
    ('orders',   'admin_note',       "ALTER TABLE orders ADD COLUMN admin_note TEXT DEFAULT ''"),
    ('orders',   'tracking_number',  "ALTER TABLE orders ADD COLUMN tracking_number TEXT DEFAULT ''"),
    ('products', 'sort_order',       "ALTER TABLE products ADD COLUMN sort_order INTEGER DEFAULT 0"),
    ('products', 'material',         "ALTER TABLE products ADD COLUMN material TEXT DEFAULT ''"),
    ('products', 'dimensions',       "ALTER TABLE products ADD COLUMN dimensions TEXT DEFAULT ''"),
    ('products', 'care_instructions',"ALTER TABLE products ADD COLUMN care_instructions TEXT DEFAULT ''"),
    ('products', 'meta_title',       "ALTER TABLE products ADD COLUMN meta_title TEXT DEFAULT ''"),
    ('products', 'meta_description', "ALTER TABLE products ADD COLUMN meta_description TEXT DEFAULT ''"),
    ('products', 'publish_at',       "ALTER TABLE products ADD COLUMN publish_at TEXT DEFAULT(datetime('now'))"),
    ('customers','tags',             "ALTER TABLE customers ADD COLUMN tags TEXT DEFAULT ''"),
    ('customers','private_note',     "ALTER TABLE customers ADD COLUMN private_note TEXT DEFAULT ''"),
    ('customers','blocked',          "ALTER TABLE customers ADD COLUMN blocked INTEGER DEFAULT 0"),
]

# PostgreSQL only — ALTER TABLE IF NOT EXISTS is safe to run every time
_PG_MIGRATIONS = [
    "ALTER TABLE ads ADD COLUMN IF NOT EXISTS start_date TEXT DEFAULT ''",
    "ALTER TABLE ads ADD COLUMN IF NOT EXISTS end_date TEXT DEFAULT ''",
    "ALTER TABLE orders   ADD COLUMN IF NOT EXISTS admin_note       TEXT DEFAULT ''",
    "ALTER TABLE orders   ADD COLUMN IF NOT EXISTS tracking_number  TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS sort_order       INTEGER DEFAULT 0",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS material         TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS dimensions       TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS care_instructions TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS meta_title       TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS meta_description TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS publish_at       TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS tags            TEXT DEFAULT ''",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS private_note    TEXT DEFAULT ''",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS blocked         BOOLEAN DEFAULT FALSE",
]

# ONLY these keys are inserted if they do NOT already exist in settings.
# init_db() uses INSERT ... DO NOTHING / INSERT OR IGNORE — NEVER overwrites.
_SETTING_DEFAULTS = {
    'tagline':          'Crafted to stand alone.',
    'hero_text':        'Where rarity meets artistry. Each piece tells a story that belongs to one soul.',
    'banner_text':      'Free shipping on orders above ₹2000 · Exclusively crafted · One of a kind',
    'banner_active':    'true',
    'logo_text':        'HENOSIS',
    'logo_image_key':   '',
    'hero_image_key':   '',
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
    'whatsapp_chat':    'false',
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
    'smtp_host':        'smtp.gmail.com',
    'smtp_port':        '587',
    'smtp_user':        '',
    'smtp_pass':        '',
    'smtp_from':        '',
    'email_notifications': 'false',
    'gst_enabled':      'false',
    'gst_percent':      '18',
    'admin_whatsapp':   '',
}

def init_db():
    """
    Safe to call on every app startup.
    • Creates tables that don't exist yet (IF NOT EXISTS).
    • Runs ALTER TABLE migrations for new columns.
    • Inserts ONLY missing setting defaults (DO NOTHING / INSERT OR IGNORE).
    • NEVER overwrites any existing data.
    """
    conn = get_conn(); cur = conn.cursor()
    try:
        if USE_PG:
            for ddl in _PG_TABLES:
                cur.execute(ddl)
            for m in _PG_MIGRATIONS:
                try:
                    cur.execute(m)
                except Exception:
                    conn.rollback()  # column already exists – ignore
            # ▼ DO NOTHING = never overwrite existing admin settings ▼
            for k, v in _SETTING_DEFAULTS.items():
                cur.execute(
                    "INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO NOTHING",
                    (k, v))
        else:
            conn.executescript(_SQ_SCRIPT)
            # SQLite ALTER TABLE (skip if column already exists)
            for table, col, sql in _SQ_MIGRATIONS:
                cur.execute(f"PRAGMA table_info({table})")
                cols = [r[1] for r in cur.fetchall()]
                if col not in cols:
                    conn.execute(sql)
            # ▼ INSERT OR IGNORE = never overwrite existing admin settings ▼
            for k, v in _SETTING_DEFAULTS.items():
                cur.execute(
                    "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                    (k, v))
        conn.commit()
    finally:
        conn.close()

# ─── Image helpers ─────────────────────────────────────────────────────────────
def _compress(raw, mime, max_px=1400, quality=85):
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert('RGB')
        w, h = img.size
        if max(w, h) > max_px:
            r = max_px / max(w, h)
            img = img.resize((int(w*r), int(h*r)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode(), 'image/jpeg'
    except Exception:
        return base64.b64encode(raw).decode(), mime

def save_site_image(raw, mime):
    b64, fm = _compress(raw, mime)
    key = str(uuid.uuid4())
    if USE_PG:
        _exec("""INSERT INTO site_images(key,data,mime_type,updated_at)
                 VALUES(%s,%s,%s,%s)
                 ON CONFLICT(key) DO UPDATE
                 SET data=EXCLUDED.data, mime_type=EXCLUDED.mime_type,
                     updated_at=EXCLUDED.updated_at""",
              (key, b64, fm, datetime.now()), commit=True)
    else:
        _exec("INSERT OR REPLACE INTO site_images(key,data,mime_type,updated_at) VALUES(?,?,?,?)",
              (key, b64, fm, datetime.now()), commit=True)
    return key

def save_product_image(pid, raw, mime, sort_order=0):
    b64, fm = _compress(raw, mime)
    iid = str(uuid.uuid4())
    _exec(f"INSERT INTO product_images(id,product_id,data,mime_type,sort_order,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH})",
          (iid, pid, b64, fm, sort_order, datetime.now()), commit=True)
    return iid

def get_site_image(key):
    r = _exec(f"SELECT data,mime_type FROM site_images WHERE key={PH}", (key,), fetch='one')
    return (r['data'], r['mime_type']) if r else (None, None)

def get_product_images(pid):
    return _exec(f"SELECT id,data,mime_type,sort_order FROM product_images WHERE product_id={PH} ORDER BY sort_order ASC, created_at ASC",
                 (pid,), fetch='all') or []

def delete_product_image(iid):
    _exec(f"DELETE FROM product_images WHERE id={PH}", (iid,), commit=True)

def delete_all_product_images(pid):
    _exec(f"DELETE FROM product_images WHERE product_id={PH}", (pid,), commit=True)

# ─── Settings ──────────────────────────────────────────────────────────────────
def get_settings():
    """
    Returns all settings. Missing keys are filled from _SETTING_DEFAULTS
    in memory only — the DB is never written during a read.
    """
    rows = _exec("SELECT key,value FROM settings", fetch='all') or []
    result = dict(_SETTING_DEFAULTS)          # start with defaults
    result.update({r['key']: r['value'] for r in rows})  # DB values win
    return result

def save_setting(key, value):
    """
    Upsert a single key. Called explicitly by admin actions only.
    Never called by init_db().
    """
    if USE_PG:
        _exec("""INSERT INTO settings(key,value) VALUES(%s,%s)
                 ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
              (key, value), commit=True)
    else:
        _exec("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
              (key, value), commit=True)

def save_settings_bulk(data: dict):
    """
    Upsert multiple keys at once. Called explicitly by admin save forms only.
    Never called by init_db().
    """
    conn = get_conn(); cur = conn.cursor()
    for k, v in data.items():
        if USE_PG:
            cur.execute("""INSERT INTO settings(key,value) VALUES(%s,%s)
                           ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""", (k, v))
        else:
            cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, v))
    conn.commit(); conn.close()

# ─── Activity / Notifications ──────────────────────────────────────────────────
def log_activity(action, detail=''):
    _exec(f"INSERT INTO activity_log(id,action,detail,created_at) VALUES({PH},{PH},{PH},{PH})",
          (str(uuid.uuid4()), action, detail, datetime.now()), commit=True)

def get_activity_log(limit=100):
    return _exec(f"SELECT * FROM activity_log ORDER BY created_at DESC LIMIT {limit}",
                 fetch='all') or []

def add_notification(ntype, title, body, link=''):
    _exec(f"INSERT INTO notifications(id,type,title,body,link,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH})",
          (str(uuid.uuid4()), ntype, title, body, link, datetime.now()), commit=True)

def get_notifications(limit=50):
    return _exec(f"SELECT * FROM notifications ORDER BY created_at DESC LIMIT {limit}",
                 fetch='all') or []

def count_unread_notifications():
    if USE_PG: r = _exec("SELECT COUNT(*) AS c FROM notifications WHERE read=FALSE", fetch='one')
    else:      r = _exec("SELECT COUNT(*) AS c FROM notifications WHERE read=0",     fetch='one')
    return int(r['c']) if r else 0

def mark_all_notifications_read():
    val = True if USE_PG else 1
    _exec(f"UPDATE notifications SET read={PH}", (val,), commit=True)

# ─── Products ──────────────────────────────────────────────────────────────────
def _np(p):
    if not p: return None
    p['only_one']     = _bool(p.get('only_one', False))
    p['featured']     = _bool(p.get('featured',  False))
    p['only_one_str'] = 'true' if p['only_one'] else 'false'
    p['featured_str'] = 'true' if p['featured'] else 'false'
    p['price']        = float(p.get('price', 0))
    p['stock']        = int(p.get('stock', 0))
    p['sort_order']   = int(p.get('sort_order', 0))
    return p

def get_all_products():
    rows = _exec("SELECT * FROM products ORDER BY sort_order ASC, created_at DESC",
                 fetch='all') or []
    return [_np(r) for r in rows]

def get_product_by_id(pid):
    return _np(_exec(f"SELECT * FROM products WHERE id={PH}", (pid,), fetch='one'))

def create_product(data):
    pid = str(uuid.uuid4())[:8].upper()
    _exec(f"""INSERT INTO products
        (id,name,price,description,category,stock,only_one,featured,sort_order,
         material,dimensions,care_instructions,meta_title,meta_description,
         publish_at,created_at)
        VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})""",
        (pid, data['name'], float(data.get('price', 0)),
         data.get('description',''), data.get('category',''),
         int(data.get('stock', 1)),
         bool(data.get('only_one', False)) if USE_PG else (1 if data.get('only_one') else 0),
         bool(data.get('featured', False)) if USE_PG else (1 if data.get('featured') else 0),
         int(data.get('sort_order', 0)),
         data.get('material',''), data.get('dimensions',''),
         data.get('care_instructions',''), data.get('meta_title',''),
         data.get('meta_description',''), datetime.now(), datetime.now()),
        commit=True)
    return pid

def update_product(pid, data):
    _exec(f"""UPDATE products SET
        name={PH}, price={PH}, description={PH}, category={PH}, stock={PH},
        only_one={PH}, featured={PH}, material={PH}, dimensions={PH},
        care_instructions={PH}, meta_title={PH}, meta_description={PH}
        WHERE id={PH}""",
        (data['name'], float(data.get('price', 0)),
         data.get('description',''), data.get('category',''),
         int(data.get('stock', 0)),
         bool(data.get('only_one', False)) if USE_PG else (1 if data.get('only_one') else 0),
         bool(data.get('featured', False)) if USE_PG else (1 if data.get('featured') else 0),
         data.get('material',''), data.get('dimensions',''),
         data.get('care_instructions',''), data.get('meta_title',''),
         data.get('meta_description',''), pid),
        commit=True)

def update_product_sort(pid, order):
    _exec(f"UPDATE products SET sort_order={PH} WHERE id={PH}", (order, pid), commit=True)

def delete_product(pid):
    _exec(f"DELETE FROM products WHERE id={PH}", (pid,), commit=True)

def decrement_stock(pid, qty, only_one):
    if only_one:
        _exec(f"UPDATE products SET stock=0 WHERE id={PH}", (pid,), commit=True)
    elif USE_PG:
        _exec(f"UPDATE products SET stock=GREATEST(0,stock-{PH}) WHERE id={PH}", (qty, pid), commit=True)
    else:
        _exec(f"UPDATE products SET stock=MAX(0,stock-{PH}) WHERE id={PH}", (qty, pid), commit=True)

def track_view(pid):
    _exec(f"INSERT INTO product_views(id,product_id,viewed_at) VALUES({PH},{PH},{PH})",
          (str(uuid.uuid4()), pid, datetime.now()), commit=True)

def get_product_view_counts():
    rows = _exec("SELECT product_id, COUNT(*) AS cnt FROM product_views GROUP BY product_id",
                 fetch='all') or []
    return {r['product_id']: int(r['cnt']) for r in rows}

# ─── Orders ────────────────────────────────────────────────────────────────────
def get_all_orders(status_filter=None):
    if status_filter:
        return _exec(f"SELECT * FROM orders WHERE status={PH} ORDER BY created_at DESC",
                     (status_filter,), fetch='all') or []
    return _exec("SELECT * FROM orders ORDER BY created_at DESC", fetch='all') or []

def get_order_by_id(oid):
    return _exec(f"SELECT * FROM orders WHERE id={PH}", (oid,), fetch='one')

def create_order(data):
    oid = str(uuid.uuid4())[:8].upper()
    _exec(f"""INSERT INTO orders(id,customer_name,email,phone,address,city,pincode,items,
        subtotal,discount_code,discount_amount,total,status,payment_status,
        note,admin_note,tracking_number,created_at)
        VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})""",
        (oid, data['customer_name'], data['email'], data['phone'],
         data['address'], data['city'], data['pincode'], data['items'],
         data.get('subtotal', 0), data.get('discount_code',''),
         data.get('discount_amount', 0), data['total'],
         'Pending', 'Unpaid', data.get('note',''), '', '', datetime.now()),
        commit=True)
    _add_timeline(oid, 'Order Placed', 'Customer placed the order')
    return oid

def update_order(oid, status, payment_status, admin_note='', tracking=''):
    old = get_order_by_id(oid)
    _exec(f"UPDATE orders SET status={PH},payment_status={PH},admin_note={PH},tracking_number={PH} WHERE id={PH}",
          (status, payment_status, admin_note, tracking, oid), commit=True)
    if old and old.get('status') != status:
        _add_timeline(oid, f'Status → {status}', admin_note or '')

def delete_order(oid):
    _exec(f"DELETE FROM orders WHERE id={PH}", (oid,), commit=True)

def _add_timeline(oid, event, note=''):
    _exec(f"INSERT INTO order_timeline(id,order_id,event,note,created_at) VALUES({PH},{PH},{PH},{PH},{PH})",
          (str(uuid.uuid4()), oid, event, note, datetime.now()), commit=True)

def get_order_timeline(oid):
    return _exec(f"SELECT * FROM order_timeline WHERE order_id={PH} ORDER BY created_at ASC",
                 (oid,), fetch='all') or []

# ─── Customers ─────────────────────────────────────────────────────────────────
def _nc(c):
    if not c: return None
    c['blocked'] = _bool(c.get('blocked', False))
    return c

def get_all_customers():
    return [_nc(r) for r in
            (_exec("SELECT * FROM customers ORDER BY total_spent DESC", fetch='all') or [])]

def get_customer_by_id(cid):
    return _nc(_exec(f"SELECT * FROM customers WHERE id={PH}", (cid,), fetch='one'))

def upsert_customer(data, order_total):
    email = data.get('email','')
    if not email: return
    existing = _exec(f"SELECT id FROM customers WHERE email={PH}", (email,), fetch='one')
    if existing:
        _exec(f"UPDATE customers SET total_orders=total_orders+1, total_spent=total_spent+{PH}, phone={PH} WHERE email={PH}",
              (float(order_total), data.get('phone',''), email), commit=True)
    else:
        _exec(f"""INSERT INTO customers(id,name,email,phone,address,city,pincode,
              total_orders,total_spent,created_at)
              VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH},1,{PH},{PH})""",
              (str(uuid.uuid4())[:8].upper(), data.get('name',''), email,
               data.get('phone',''), data.get('address',''), data.get('city',''),
               data.get('pincode',''), float(order_total), datetime.now()), commit=True)

def update_customer_notes(cid, tags, private_note, blocked):
    val = bool(blocked) if USE_PG else (1 if blocked else 0)
    _exec(f"UPDATE customers SET tags={PH},private_note={PH},blocked={PH} WHERE id={PH}",
          (tags, private_note, val, cid), commit=True)

def delete_customer(cid):
    _exec(f"DELETE FROM customers WHERE id={PH}", (cid,), commit=True)

def get_customer_by_id(cid):
    return _nc(_exec(f"SELECT * FROM customers WHERE id={PH}", (cid,), fetch='one'))

def is_blocked(email):
    r = _exec(f"SELECT blocked FROM customers WHERE email={PH}", (email,), fetch='one')
    return _bool(r['blocked']) if r else False

# ─── Discounts ─────────────────────────────────────────────────────────────────
def _nd(d):
    if not d: return None
    d['active']     = _bool(d.get('active', True))
    d['active_str'] = 'true' if d['active'] else 'false'
    d['value']      = float(d.get('value', 0))
    d['min_order']  = float(d.get('min_order', 0))
    d['uses_left']  = int(d.get('uses_left', 0))
    return d

def get_all_discounts():
    return [_nd(r) for r in
            (_exec("SELECT * FROM discounts ORDER BY created_at DESC", fetch='all') or [])]

def get_discount(code):
    return _nd(_exec(f"SELECT * FROM discounts WHERE UPPER(code)=UPPER({PH})", (code,), fetch='one'))

def create_discount(data):
    code = data['code'].upper()
    if USE_PG:
        _exec("""INSERT INTO discounts(code,discount_type,value,min_order,uses_left,active,created_at)
                 VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(code) DO NOTHING""",
              (code, data['discount_type'], float(data['value']),
               float(data.get('min_order', 0)), int(data.get('uses_left', 100)),
               True, datetime.now()), commit=True)
    else:
        _exec("""INSERT OR IGNORE INTO discounts(code,discount_type,value,min_order,uses_left,active,created_at)
                 VALUES(?,?,?,?,?,?,?)""",
              (code, data['discount_type'], float(data['value']),
               float(data.get('min_order', 0)), int(data.get('uses_left', 100)),
               1, datetime.now()), commit=True)

def toggle_discount(code):
    if USE_PG:
        _exec("UPDATE discounts SET active=NOT active WHERE UPPER(code)=UPPER(%s)", (code,), commit=True)
    else:
        _exec("UPDATE discounts SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE UPPER(code)=UPPER(?)",
              (code,), commit=True)

def decrement_discount(code):
    if USE_PG:
        _exec("UPDATE discounts SET uses_left=GREATEST(0,uses_left-1) WHERE UPPER(code)=UPPER(%s)",
              (code,), commit=True)
    else:
        _exec("UPDATE discounts SET uses_left=MAX(0,uses_left-1) WHERE UPPER(code)=UPPER(?)",
              (code,), commit=True)

def delete_discount(code):
    _exec(f"DELETE FROM discounts WHERE UPPER(code)=UPPER({PH})", (code,), commit=True)

# ─── Reviews ───────────────────────────────────────────────────────────────────
def _nr(r):
    if not r: return None
    r['approved']     = _bool(r.get('approved', False))
    r['approved_str'] = 'true' if r['approved'] else 'false'
    r['rating']       = int(r.get('rating', 5))
    return r

def get_all_reviews():
    return [_nr(r) for r in
            (_exec("SELECT * FROM reviews ORDER BY created_at DESC", fetch='all') or [])]

def get_reviews_for_product(pid):
    q = (f"SELECT * FROM reviews WHERE product_id={PH} AND approved=TRUE  ORDER BY created_at DESC"
         if USE_PG else
         f"SELECT * FROM reviews WHERE product_id={PH} AND approved=1     ORDER BY created_at DESC")
    return [_nr(r) for r in (_exec(q, (pid,), fetch='all') or [])]

def create_review(data):
    _exec(f"INSERT INTO reviews(id,product_id,customer_name,rating,comment,approved,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH})",
          (str(uuid.uuid4())[:8].upper(), data['product_id'], data['customer_name'],
           int(data.get('rating', 5)), data['comment'],
           False if USE_PG else 0, datetime.now()), commit=True)

def approve_review(rid):
    _exec(f"UPDATE reviews SET approved={PH} WHERE id={PH}",
          (True if USE_PG else 1, rid), commit=True)

def delete_review(rid):
    _exec(f"DELETE FROM reviews WHERE id={PH}", (rid,), commit=True)

# ─── Pages ─────────────────────────────────────────────────────────────────────
def _npg(p):
    if not p: return None
    p['published'] = _bool(p.get('published', True))
    return p

def get_all_pages():
    return [_npg(r) for r in
            (_exec("SELECT * FROM pages ORDER BY created_at DESC", fetch='all') or [])]

def get_page_by_slug(slug):
    return _npg(_exec(f"SELECT * FROM pages WHERE slug={PH}", (slug,), fetch='one'))

def get_page_by_id(pid):
    return _npg(_exec(f"SELECT * FROM pages WHERE id={PH}", (pid,), fetch='one'))

def save_page(data):
    pid = data.get('id') or str(uuid.uuid4())[:8]
    existing = get_page_by_id(pid)
    pub = bool(data.get('published', True)) if USE_PG else (1 if data.get('published', True) else 0)
    if existing:
        _exec(f"UPDATE pages SET title={PH},content={PH},published={PH} WHERE id={PH}",
              (data['title'], data.get('content',''), pub, pid), commit=True)
    else:
        if USE_PG:
            _exec("""INSERT INTO pages(id,title,slug,content,published,created_at)
                     VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(slug) DO NOTHING""",
                  (pid, data['title'], data['slug'], data.get('content',''), pub, datetime.now()),
                  commit=True)
        else:
            _exec("""INSERT OR IGNORE INTO pages(id,title,slug,content,published,created_at)
                     VALUES(?,?,?,?,?,?)""",
                  (pid, data['title'], data['slug'], data.get('content',''), pub, datetime.now()),
                  commit=True)
    return pid

def delete_page(pid):
    _exec(f"DELETE FROM pages WHERE id={PH}", (pid,), commit=True)

# ─── Expenses ──────────────────────────────────────────────────────────────────
def get_all_expenses():
    return _exec("SELECT * FROM expenses ORDER BY expense_date DESC, created_at DESC",
                 fetch='all') or []

def create_expense(data):
    _exec(f"INSERT INTO expenses(id,description,amount,category,expense_date,created_at) VALUES({PH},{PH},{PH},{PH},{PH},{PH})",
          (str(uuid.uuid4())[:8], data['description'], float(data['amount']),
           data.get('category','Other'), data.get('expense_date',''), datetime.now()), commit=True)

def delete_expense(eid):
    _exec(f"DELETE FROM expenses WHERE id={PH}", (eid,), commit=True)

def get_total_expenses():
    r = _exec("SELECT SUM(amount) AS t FROM expenses", fetch='one')
    return float(r['t']) if r and r['t'] else 0.0

# ─── Restock notifications ──────────────────────────────────────────────────────
def add_restock_notify(pid, email):
    existing = _exec(f"SELECT id FROM notify_restock WHERE product_id={PH} AND email={PH}",
                     (pid, email), fetch='one')
    if not existing:
        _exec(f"INSERT INTO notify_restock(id,product_id,email,created_at) VALUES({PH},{PH},{PH},{PH})",
              (str(uuid.uuid4()), pid, email, datetime.now()), commit=True)

# ─── Analytics ─────────────────────────────────────────────────────────────────
def revenue_by_day(days=7):
    from collections import defaultdict
    dd = defaultdict(float)
    for o in get_all_orders():
        dd[str(o.get('created_at',''))[:10]] += float(o.get('total', 0))
    return sorted(dd.items())[-days:]

def revenue_by_month():
    from collections import defaultdict
    mm = defaultdict(float)
    for o in get_all_orders():
        mm[str(o.get('created_at',''))[:7]] += float(o.get('total', 0))
    return sorted(mm.items())

# ─── Ads ───────────────────────────────────────────────────────────────────────
def _nad(a):
    if not a: return None
    a['active'] = _bool(a.get('active', True))
    a['active_str'] = 'true' if a['active'] else 'false'
    a['sort_order'] = int(a.get('sort_order', 0))
    return a

def get_all_ads():
    return [_nad(r) for r in (_exec("SELECT * FROM ads ORDER BY sort_order ASC, created_at DESC", fetch='all') or [])]

def get_ads_for_position(position):
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    rows = _exec(f"SELECT * FROM ads WHERE position={PH} ORDER BY sort_order ASC", (position,), fetch='all') or []
    active = []
    for r in rows:
        a = _nad(r)
        if not a['active']: continue
        # Date range check
        sd = a.get('start_date', '')
        ed = a.get('end_date', '')
        if sd and today < sd: continue
        if ed and today > ed: continue
        active.append(a)
    return active

def get_ad_by_id(aid):
    return _nad(_exec(f"SELECT * FROM ads WHERE id={PH}", (aid,), fetch='one'))

def create_ad(data):
    aid = str(uuid.uuid4())[:8].upper()
    active_val = bool(data.get('active', True)) if USE_PG else (1 if data.get('active', True) else 0)
    _exec(f"""INSERT INTO ads(id,name,type,position,image_key,link_url,link_text,
        bg_color,text_color,content,active,sort_order,start_date,end_date,created_at)
        VALUES({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})""",
        (aid, data.get('name',''), data.get('type','banner'), data.get('position','top'),
         data.get('image_key',''), data.get('link_url',''), data.get('link_text',''),
         data.get('bg_color','#1a1a1a'), data.get('text_color','#faf8f4'),
         data.get('content',''), active_val, int(data.get('sort_order',0)),
         data.get('start_date',''), data.get('end_date',''), datetime.now()), commit=True)
    return aid

def update_ad(aid, data):
    active_val = bool(data.get('active', True)) if USE_PG else (1 if data.get('active', True) else 0)
    _exec(f"""UPDATE ads SET name={PH},type={PH},position={PH},image_key={PH},
        link_url={PH},link_text={PH},bg_color={PH},text_color={PH},content={PH},
        active={PH},sort_order={PH},start_date={PH},end_date={PH} WHERE id={PH}""",
        (data.get('name',''), data.get('type','banner'), data.get('position','top'),
         data.get('image_key',''), data.get('link_url',''), data.get('link_text',''),
         data.get('bg_color','#1a1a1a'), data.get('text_color','#faf8f4'),
         data.get('content',''), active_val, int(data.get('sort_order',0)),
         data.get('start_date',''), data.get('end_date',''), aid), commit=True)

def delete_ad(aid):
    _exec(f"DELETE FROM ads WHERE id={PH}", (aid,), commit=True)

def toggle_ad(aid):
    if USE_PG: _exec("UPDATE ads SET active=NOT active WHERE id=%s", (aid,), commit=True)
    else:      _exec("UPDATE ads SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (aid,), commit=True)

# ─── Media Library ─────────────────────────────────────────────────────────────
def save_media(name, raw, mime, usage='general'):
    try:
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(raw))
        w, h = img.size
    except:
        w, h = 0, 0
    b64, fm = _compress(raw, mime, max_px=2000, quality=88)
    key = str(uuid.uuid4())
    mid = str(uuid.uuid4())[:8]
    if USE_PG:
        _exec("""INSERT INTO media_library(id,name,key,data,mime_type,usage,width,height,created_at)
                 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                 ON CONFLICT(key) DO UPDATE SET data=EXCLUDED.data,updated_at=NOW()""",
              (mid, name, key, b64, fm, usage, w, h, datetime.now()), commit=True)
    else:
        _exec("""INSERT OR REPLACE INTO media_library(id,name,key,data,mime_type,usage,width,height,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
              (mid, name, key, b64, fm, usage, w, h, datetime.now()), commit=True)
    return key, mid

def get_all_media():
    rows = _exec("SELECT id,name,key,mime_type,usage,width,height,created_at FROM media_library ORDER BY created_at DESC",
                 fetch='all') or []
    return rows

def get_media_by_key(key):
    return _exec(f"SELECT data,mime_type FROM media_library WHERE key={PH}", (key,), fetch='one')

def delete_media(mid):
    _exec(f"DELETE FROM media_library WHERE id={PH}", (mid,), commit=True)

def update_media_usage(key, usage):
    _exec(f"UPDATE media_library SET usage={PH} WHERE key={PH}", (usage, key), commit=True)
