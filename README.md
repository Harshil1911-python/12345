# HENOSIS — Luxury Imitation Jewellery
## Production-Ready Flask + PostgreSQL Ecommerce

---

## 🚀 Deploy to Render (3 steps)

### Step 1 — Push to GitHub
```bash
git init && git add . && git commit -m "Henosis v1"
git remote add origin https://github.com/YOUR_USER/henosis.git
git push -u origin main
```

### Step 2 — Deploy
1. [render.com](https://render.com) → **New → Blueprint**
2. Connect your GitHub repo
3. Render reads `render.yaml` → auto-creates web service + PostgreSQL
4. Click **Apply** → live in ~3 minutes

### Step 3 — Set your password (optional)
```bash
python3 -c "import hashlib; print(hashlib.sha256('YourPass'.encode()).hexdigest())"
```
Render Dashboard → Service → Environment → update `ADMIN_PASSWORD_HASH`

---

## 🔐 Admin Access
- URL: `https://yoursite.com/henosis-admin`  
- OR: **click footer logo 5 times quickly**
- Email: `henosis4india@gmail.com`
- Password: `Henosis@2024`

---

## ✅ Why Data is Permanent
- PostgreSQL on Render = managed, dedicated database
- **Not tied to web service** — redeploys/restarts never touch the DB
- `init_db()` uses `INSERT ... DO NOTHING` — **never overwrites** admin changes
- All images stored as base64 in PostgreSQL — zero filesystem dependency
- `--workers 1 --preload` prevents race conditions on startup

---

## 📋 Environment Variables

| Variable | Value | How set |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Auto from render.yaml |
| `SECRET_KEY` | Random 32-byte key | Auto-generated |
| `ADMIN_EMAIL` | henosis4india@gmail.com | render.yaml |
| `ADMIN_PASSWORD_HASH` | SHA-256 of your password | render.yaml |

---

## ✨ Features

### Store
- Luxury homepage · Shop with search/filter/sort · Product detail with reviews
- Cart drawer · Checkout with discount codes + order notes
- WhatsApp chat button · Welcome popup · Maintenance mode
- Custom pages (built from admin — no code)

### Admin Panel
| Section | Features |
|---|---|
| **Dashboard** | Revenue, orders, 7-day chart, low-stock alerts, notifications |
| **Products** | Add/Edit/Delete/Duplicate, drag-drop reorder, multi-image, AI description |
| **Orders** | Filter, bulk update, WhatsApp notify, invoice PDF, CSV export |
| **Customers** | Profiles, order history, tags, block, CSV export |
| **Discounts** | % or flat codes, usage limits, enable/disable |
| **Reviews** | Approve/delete customer reviews |
| **Analytics** | Revenue chart, order breakdown, category sales, top customers |
| **Expenses & P&L** | Track expenses, net profit dashboard |
| **Custom Pages** | Visual block builder — no code needed |
| **Settings (8 tabs)** | Brand, Hero, Banner, Shop, Colors, SEO, Pages, Advanced |
| **Activity Log** | Every admin action logged |
| **Quick Search** | Press `/` anywhere in admin |
| **Notifications** | Real-time bell, auto-dismiss |

---

## 💻 Local Development
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py   # → http://localhost:5000 (SQLite auto-created)
```
