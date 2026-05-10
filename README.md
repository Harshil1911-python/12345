# HENOSIS — Luxury Imitation Jewellery

Full-stack luxury ecommerce. Pure PostgreSQL on Render — all data including images stored in the database permanently.

---

## 🚀 Local Development

```bash
cd henosis
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
→ http://localhost:5000  (SQLite auto-created in `data/henosis.db`)

---

## ☁️ Deploy to Render (Permanent PostgreSQL)

### One-click with Blueprint:
1. Push this folder to a GitHub repo
2. Go to **render.com** → New → **Blueprint**
3. Connect your repo (Render reads `render.yaml` automatically)
4. Render creates:
   - ✅ Web service (Flask app)
   - ✅ PostgreSQL database (free tier, **persistent forever**)
   - ✅ `DATABASE_URL` injected automatically
5. Click **Deploy**
6. After first deploy, update `ADMIN_PASSWORD_HASH` env var with your hashed password

### Manual deploy:
1. New → Web Service → connect repo
2. Build: `pip install -r requirements.txt`
3. Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
4. Add env vars:
   - `SECRET_KEY` → any random string (or use "Generate" button)
   - `DATABASE_URL` → from a Render PostgreSQL database you create
   - `ADMIN_EMAIL` → henosis4india@gmail.com
   - `ADMIN_PASSWORD_HASH` → SHA-256 hash of your password

### Generate password hash:
```python
import hashlib
print(hashlib.sha256("YourPassword".encode()).hexdigest())
```

---

## 🔐 Admin Access

**URL:** `https://yoursite.com/henosis-admin`
**Or:** Click the footer logo **5 times quickly**

| | |
|---|---|
| Email | henosis4india@gmail.com |
| Default Password | Henosis@2024 |

Change password at: Admin → Change Password

---

## 🗄️ Why PostgreSQL is Permanent on Render

Render's free PostgreSQL database:
- Lives on dedicated managed infrastructure
- **Not tied to your web service** — upgrading/redeploying your app never touches the DB
- Your products, orders, customers, images all survive restarts, redeploys, and upgrades
- Images stored as base64 directly in the DB — no S3, no filesystem, nothing to lose

---

## ✨ Feature List

### Store
- Luxury homepage with hero, featured products, gallery, brand story
- Shop with search, category filter, price sort
- Product pages with image gallery, customer reviews, related items, WhatsApp link
- Cart drawer + full cart page
- Checkout with discount codes, order notes
- WhatsApp floating chat button
- Welcome popup
- Maintenance mode

### Admin Panel (`/henosis-admin` or 5× footer logo)
| | |
|---|---|
| **Dashboard** | Revenue, orders, low stock alert, 7-day revenue chart |
| **Products** | Add/Edit/Delete/Duplicate, multi-image upload (stored in DB) |
| **Orders** | Filter by status, update status & payment, admin notes, CSV export, delete |
| **Customers** | View all, spend stats, delete, CSV export |
| **Discounts** | Create % or flat codes, usage limits, enable/disable |
| **Reviews** | Approve/delete customer reviews |
| **Analytics** | Monthly revenue chart, order breakdown, category sales, top customers |
| **Settings (7 tabs)** | Brand, Hero, Banner, Shop, Colors, SEO, Advanced |
| **Change Password** | Secure in-app password update |

### Settings
- **Brand** — Logo (image or text), footer, contact, social links, WhatsApp
- **Hero** — Tagline, subtext, background image (all stored in DB)
- **Banner** — Announcement bar, show/hide
- **Shop** — Currency symbol, free shipping threshold, low stock alert, reviews on/off
- **Colors** — Primary gold + accent color pickers
- **SEO** — Meta title, description, Google Analytics ID
- **Advanced** — Maintenance mode, welcome popup

---

## 📁 Structure

```
henosis/
├── app.py          # All Flask routes
├── db.py           # PostgreSQL/SQLite abstraction + image storage
├── requirements.txt
├── Procfile
├── render.yaml     # Render Blueprint (auto-creates DB)
├── runtime.txt
├── static/
│   ├── css/main.css
│   └── js/main.js
└── templates/
    ├── base.html, index.html, shop.html, product.html
    ├── cart.html, checkout.html, order_success.html
    ├── about.html, maintenance.html
    └── admin/  (10 templates)
```
