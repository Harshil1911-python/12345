# HENOSIS — Luxury Imitation Jewellery

A full-stack luxury ecommerce website built with Flask, file-based storage, and a premium editorial design.

---

## 🚀 Quick Start (Local)

```bash
# 1. Clone / download project
cd henosis

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python app.py
```

Visit → http://localhost:5000

---

## 🔐 Admin Access

URL: `http://localhost:5000/henosis-admin`

| Field    | Value                         |
|----------|-------------------------------|
| Email    | henosis4india@gmail.com       |
| Password | Henosis@2024                  |

⚠️ Change the password in `app.py` → `ADMIN_PASSWORD` before going live.
To change: `hashlib.sha256('YourNewPassword'.encode()).hexdigest()`

---

## 📁 File Structure

```
henosis/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── Procfile               # For Railway/Render
├── render.yaml            # Render config
├── runtime.txt            # Python version
├── data/                  # Auto-created data storage
│   ├── products.csv
│   ├── products.dat
│   ├── orders.csv
│   ├── orders.dat
│   ├── settings.csv
│   ├── settings.dat
│   └── customers.csv
├── static/
│   ├── css/main.css       # Full design system
│   ├── js/main.js         # Cart, animations, interactions
│   └── uploads/           # Product & logo images
└── templates/
    ├── base.html           # Shared layout with nav/footer
    ├── index.html          # Homepage
    ├── shop.html           # Product listing
    ├── product.html        # Product detail
    ├── checkout.html       # Checkout form
    ├── order_success.html  # Confirmation
    ├── about.html          # Brand story
    └── admin/
        ├── base.html       # Admin layout
        ├── login.html      # Admin login
        ├── dashboard.html  # Stats & overview
        ├── products.html   # Product list
        ├── product_form.html # Add/edit product
        ├── orders.html     # Order management
        └── settings.html   # Site settings
```

---

## ☁️ Deploy to Render (Free Tier)

1. Push code to GitHub
2. Go to https://render.com → New Web Service
3. Connect your repo
4. Settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Add environment variable: `SECRET_KEY` → any random string
6. Add a Disk: mount at `/opt/render/project/src/data` (for persistent data)
7. Deploy!

---

## ☁️ Deploy to Railway

1. Push code to GitHub
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Add environment variable: `SECRET_KEY` → any random string
4. Railway auto-detects the Procfile
5. Deploy!

---

## ✏️ Admin Features

| Feature              | How                                   |
|----------------------|---------------------------------------|
| Add products         | Admin → Products → Add Product        |
| Edit products        | Admin → Products → Edit               |
| Delete products      | Admin → Products → Delete             |
| Manage orders        | Admin → Orders                        |
| Update order status  | Admin → Orders → Update               |
| Change tagline       | Admin → Settings                      |
| Change hero text     | Admin → Settings                      |
| Change logo          | Admin → Settings → Upload Logo        |
| Change banner        | Admin → Settings                      |

---

## 💎 Design System

**Colors:**
- Ivory: `#faf8f4` — Background
- Champagne Gold: `#c9a96e` — Accents
- Gold: `#b8965a` — CTAs, prices
- Charcoal: `#1a1a1a` — Headers, dark sections
- Cream: `#f5f0e8` — Card backgrounds

**Fonts:**
- Headings: Cormorant Garamond (serif)
- Body: Raleway (sans-serif)

---

## 📦 Data Storage

All data is automatically stored in flat files:

- `data/products.csv` + `data/products.dat` — Product catalogue
- `data/orders.csv` + `data/orders.dat` — Customer orders
- `data/settings.csv` + `data/settings.dat` — Site settings
- `static/uploads/` — All uploaded images

No database required. Files are auto-created on first run.

---

## 🔒 Security Notes

- Admin route is hidden at `/henosis-admin` (not linked publicly)
- Password is SHA-256 hashed
- Flask session-based authentication
- Change `SECRET_KEY` in production (use environment variable)
- Change default admin password before deploying

---

Made with ♥ for Henosis.
