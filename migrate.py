#!/usr/bin/env python3
"""
migrate.py — Run safe database migrations manually.
Usage:
  python migrate.py            # runs all migrations
  python migrate.py --status   # shows current table columns
"""
import sys, db

def status():
    conn = db.get_conn(); cur = conn.cursor()
    tables = ['products','orders','customers','settings','discounts',
              'reviews','pages','expenses','notifications','activity_log']
    for t in tables:
        if db.USE_PG:
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}' ORDER BY ordinal_position")
            cols = [r[0] for r in cur.fetchall()]
        else:
            cur.execute(f"PRAGMA table_info({t})")
            rows = cur.fetchall()
            cols = [r[1] for r in rows] if rows else ['(table not found)']
        print(f"  {t}: {', '.join(cols)}")
    conn.close()

def migrate():
    print(f"Running migrations on {'PostgreSQL' if db.USE_PG else 'SQLite'}...")
    db.init_db()
    print("✅ All migrations complete. No data was overwritten.")

if '--status' in sys.argv:
    print("Current schema:")
    status()
else:
    migrate()
    print("\nTable status after migration:")
    status()
