# HENOSIS — Luxury Imitation Jewellery

Full-stack luxury ecommerce with Flask + PostgreSQL (Render) / SQLite (local).

---

## 🚀 Quick Start (Local — SQLite)

```bash
cd henosis
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
→ http://localhost:5000  (uses SQLite automatically — no setup needed)

---

## ☁️ Deploy to Render (PostgreSQL — Persistent)

1. Push to GitHub
2. Go to **render.com** → New → **Blueprint**
3. Connect your repo — Render reads `render.yaml` automatically
4. It creates:
   - A **Web Service** (your Flask app)
   - A **PostgreSQL database** (free tier, persistent)
   - Injects `DATABASE_URL` automatically
5. Add env var: `ADMIN_PASSWORD_HASH` = SHA-256 hash of your password
6. Deploy!

### How DATABASE_URL works
| Environment | Database | Set by |
|---|---|---|
| Local dev | SQLite (`data/henosis.db`) | Auto (no config needed) |
| Render | PostgreSQL | `render.yaml` → `fromDatabase` |
| Railway | PostgreSQL | Add `DATABASE_URL` env var manually |

---

## 🔐 Admin Access

URL: `http://yoursite.com/henosis-admin`
Or: **Click the footer logo 5 times quickly**

| Field | Default |
|---|---|
| Email | henosis4india@gmail.com |
| Password | Henosis@2024 |

**Change password:** Admin → Change Password  
Then set `ADMIN_PASSWORD_HASH` env var on Render to the new SHA-256 hash.

---

## ✨ Features

### Store
- Luxury homepage with hero, featured products, gallery, brand story
- Shop with category filter, search, sort (price / newest)
- Product detail with image gallery, reviews, related products
- Cart drawer + full cart page
- Checkout with discount codes, order notes
- WhatsApp chat button (configurable)
- Welcome popup (configurable)
- Maintenance mode

### Admin Panel (hidden at `/henosis-admin`)
| Section | Features |
|---|---|
| **Dashboard** | Revenue stats, recent orders, low stock alerts, revenue chart |
| **Products** | Add/edit/delete/duplicate, image upload, One-of-a-Kind toggle |
| **Orders** | Status filter, update status/payment, admin notes, CSV export, delete |
| **Customers** | View all, total orders & spend, delete, CSV export |
| **Discounts** | Create codes (% or flat), usage limits, enable/disable/delete |
| **Reviews** | Approve/delete customer reviews |
| **Analytics** | Revenue chart, order status breakdown, category sales, top customers |
| **Settings** | 7-tab settings: Brand, Hero, Banner, Shop, Colors, SEO, Advanced |
| **Change Password** | Secure password update |

### Settings Tabs
- **Brand** — Logo (text or image), footer text, contact info, social links, WhatsApp
- **Hero** — Tagline, subtext, background image, live preview
- **Banner** — Announcement bar text, show/hide toggle
- **Shop** — Currency symbol, free shipping threshold, low stock alert, show reviews
- **Colors** — Primary gold + accent champagne color pickers
- **SEO** — Meta title, meta description, Google Analytics ID
- **Advanced** — Maintenance mode, welcome popup (title, text, CTA)

---

## 📁 Project Structure

```
henosis/
├── app.py              # Flask routes + logic
├── db.py               # PostgreSQL/SQLite abstraction layer
├── requirements.txt    # Dependencies
├── Procfile            # Gunicorn start command
├── render.yaml         # Render Blueprint (app + DB)
├── runtime.txt         # Python 3.11
├── data/               # SQLite DB (local dev only)
│   └── henosis.db
├── static/
│   ├── css/main.css    # Full luxury design system
│   ├── js/main.js      # Cart, animations, interactions
│   └── uploads/        # Product & logo images
└── templates/
    ├── base.html        # Nav, footer, cart drawer, popups
    ├── index.html       # Homepage
    ├── shop.html        # Product listing
    ├── product.html     # Product detail + reviews
    ├── cart.html        # Cart page
    ├── checkout.html    # Checkout + discount codes
    ├── order_success.html
    ├── about.html
    ├── maintenance.html
    └── admin/           # All admin templates
```

---

## 🔒 Security

- Admin route hidden (not linked publicly)
- Password SHA-256 hashed
- Flask session-based auth
- Protected admin routes via decorator
- Set `SECRET_KEY` env var in production (auto-generated on Render via `generateValue: true`)

---

Made with ♥ for Henosis — *Crafted to stand alone.*
