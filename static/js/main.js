/* ─── Cart State ─────────────────────────────────────────────────────────────── */
let cart = JSON.parse(localStorage.getItem('henosis_cart') || '[]');

function saveCart() {
  localStorage.setItem('henosis_cart', JSON.stringify(cart));
  renderCart();
  updateCartCount();
}

function updateCartCount() {
  const total = cart.reduce((s, i) => s + i.qty, 0);
  document.querySelectorAll('#cartCount').forEach(el => {
    el.textContent = total;
    el.style.display = total > 0 ? 'flex' : 'none';
  });
}

function addToCart(id, name, price, image, onlyOne) {
  if (onlyOne === 'true' || onlyOne === true) {
    // Only one in the world — replace or add single qty
    const exists = cart.find(i => i.id === id);
    if (!exists) cart.push({ id, name, price: parseFloat(price), image, qty: 1, onlyOne: true });
  } else {
    const existing = cart.find(i => i.id === id);
    if (existing) existing.qty += 1;
    else cart.push({ id, name, price: parseFloat(price), image, qty: 1, onlyOne: false });
  }
  saveCart();
  openCart();
  showToast(`${name} added to your selection`);
}

function removeFromCart(id) {
  cart = cart.filter(i => i.id !== id);
  saveCart();
}

function renderCart() {
  const container = document.getElementById('cartItems');
  const totalEl   = document.getElementById('cartTotal');
  if (!container) return;

  if (cart.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding:60px 20px">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin:0 auto 16px;color:var(--beige)">
          <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/>
        </svg>
        <p style="font-size:.85rem;color:var(--gray-light)">Your selection is empty</p>
      </div>`;
    if (totalEl) totalEl.textContent = '₹0';
    return;
  }

  container.innerHTML = cart.map(item => `
    <div class="cart-item">
      <div class="cart-item-img" style="background:var(--cream);display:flex;align-items:center;justify-content:center;">
        ${item.image
          ? `<img src="/uploads/${item.image}" alt="${item.name}" style="width:100%;height:100%;object-fit:cover;">`
          : `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="color:var(--beige)"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`
        }
      </div>
      <div class="cart-item-info">
        <div class="cart-item-name">${item.name}</div>
        <div class="cart-item-price">₹${(item.price * item.qty).toLocaleString('en-IN')}</div>
        ${item.onlyOne ? '<div style="font-size:.58rem;letter-spacing:.12em;text-transform:uppercase;color:var(--champagne);margin-top:4px;">One of a kind</div>' : `
        <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
          <button onclick="changeQty('${item.id}',-1)" style="width:22px;height:22px;border:1px solid var(--beige);background:none;cursor:pointer;font-size:.9rem;display:flex;align-items:center;justify-content:center;">−</button>
          <span style="font-size:.8rem;">${item.qty}</span>
          <button onclick="changeQty('${item.id}',1)" style="width:22px;height:22px;border:1px solid var(--beige);background:none;cursor:pointer;font-size:.9rem;display:flex;align-items:center;justify-content:center;">+</button>
        </div>`}
      </div>
      <button class="cart-item-remove" onclick="removeFromCart('${item.id}')">Remove</button>
    </div>
  `).join('');

  const total = cart.reduce((s, i) => s + i.price * i.qty, 0);
  if (totalEl) totalEl.textContent = `₹${total.toLocaleString('en-IN')}`;
}

function changeQty(id, delta) {
  const item = cart.find(i => i.id === id);
  if (!item) return;
  item.qty = Math.max(1, item.qty + delta);
  saveCart();
}

/* ─── Cart Drawer ────────────────────────────────────────────────────────────── */
function openCart() {
  document.getElementById('cartDrawer')?.classList.add('open');
  document.getElementById('cartOverlay')?.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeCart() {
  document.getElementById('cartDrawer')?.classList.remove('open');
  document.getElementById('cartOverlay')?.classList.remove('open');
  document.body.style.overflow = '';
}
function toggleCart() {
  const drawer = document.getElementById('cartDrawer');
  if (drawer?.classList.contains('open')) closeCart();
  else openCart();
}

/* ─── Toast ──────────────────────────────────────────────────────────────────── */
function showToast(message) {
  let toast = document.getElementById('henosisToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'henosisToast';
    toast.style.cssText = `
      position:fixed;bottom:32px;left:50%;transform:translateX(-50%) translateY(20px);
      background:var(--charcoal);color:var(--ivory);padding:14px 28px;
      font-family:var(--font-body);font-size:.78rem;letter-spacing:.08em;
      z-index:9999;opacity:0;transition:all .4s cubic-bezier(.16,1,.3,1);
      pointer-events:none;white-space:nowrap;border-left:2px solid var(--gold);
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.opacity = '1';
  toast.style.transform = 'translateX(-50%) translateY(0)';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(20px)';
  }, 3000);
}

/* ─── Scroll Animations ──────────────────────────────────────────────────────── */
function initReveal() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        observer.unobserve(e.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
}

/* ─── Nav scroll ─────────────────────────────────────────────────────────────── */
function initNav() {
  const nav = document.getElementById('nav');
  if (!nav) return;
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 40);
  }, { passive: true });
}

/* ─── Product Image Gallery ──────────────────────────────────────────────────── */
function initProductGallery() {
  const thumbs = document.querySelectorAll('.product-thumb');
  const mainImg = document.getElementById('mainProductImage');
  if (!thumbs.length || !mainImg) return;
  thumbs.forEach(t => {
    t.addEventListener('click', () => {
      thumbs.forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      const src = t.dataset.src;
      mainImg.style.opacity = '0';
      mainImg.style.transform = 'scale(1.02)';
      setTimeout(() => {
        mainImg.src = src;
        mainImg.style.opacity = '1';
        mainImg.style.transform = 'scale(1)';
      }, 200);
    });
  });
  if (mainImg) {
    mainImg.style.transition = 'opacity .3s ease, transform .3s ease';
  }
}

/* ─── Checkout page ──────────────────────────────────────────────────────────── */
function initCheckout() {
  const form = document.getElementById('checkoutForm');
  if (!form) return;

  // Render order summary
  renderCheckoutSummary();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (cart.length === 0) { showToast('Your cart is empty'); return; }

    const btn = form.querySelector('[type="submit"]');
    btn.textContent = 'Placing Order...';
    btn.disabled = true;

    const customer = {
      name:    form.querySelector('[name="name"]').value,
      email:   form.querySelector('[name="email"]').value,
      phone:   form.querySelector('[name="phone"]').value,
      address: form.querySelector('[name="address"]').value,
      city:    form.querySelector('[name="city"]').value,
      pincode: form.querySelector('[name="pincode"]').value,
    };

    try {
      const res = await fetch('/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cart, customer }),
      });
      const data = await res.json();
      if (data.success) {
        cart = [];
        saveCart();
        window.location.href = `/order-success?id=${data.order_id}`;
      } else {
        showToast(data.error || 'Something went wrong');
        btn.textContent = 'Place Order';
        btn.disabled = false;
      }
    } catch {
      showToast('Network error. Please try again.');
      btn.textContent = 'Place Order';
      btn.disabled = false;
    }
  });
}

function renderCheckoutSummary() {
  const container = document.getElementById('summaryItems');
  const totalEl   = document.getElementById('summaryTotal');
  if (!container) return;

  if (cart.length === 0) {
    container.innerHTML = '<p style="font-size:.85rem;color:var(--gray-mid)">No items in cart</p>';
    return;
  }
  container.innerHTML = cart.map(item => `
    <div class="summary-item">
      <span class="summary-item-name">${item.name} <span style="color:var(--gray-light)">×${item.qty}</span></span>
      <span class="summary-item-price">₹${(item.price * item.qty).toLocaleString('en-IN')}</span>
    </div>
  `).join('');

  const total = cart.reduce((s, i) => s + i.price * i.qty, 0);
  if (totalEl) totalEl.textContent = `₹${total.toLocaleString('en-IN')}`;
}

/* ─── Cursor Glow (desktop) ──────────────────────────────────────────────────── */
function initCursorGlow() {
  if (window.matchMedia('(hover: none)').matches) return;
  const glow = document.createElement('div');
  glow.style.cssText = `
    position:fixed;width:300px;height:300px;border-radius:50%;pointer-events:none;
    background:radial-gradient(circle,rgba(201,169,110,0.04) 0%,transparent 70%);
    transform:translate(-50%,-50%);z-index:0;transition:opacity .3s;
  `;
  document.body.appendChild(glow);
  document.addEventListener('mousemove', e => {
    glow.style.left = e.clientX + 'px';
    glow.style.top  = e.clientY + 'px';
  }, { passive: true });
}

/* ─── Init ───────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  updateCartCount();
  renderCart();
  initReveal();
  initNav();
  initProductGallery();
  initCheckout();
  initCursorGlow();
});

/* ─── Page Loader ────────────────────────────────────────────────────────────── */
function initPageLoader() {
  const loader = document.getElementById('pageLoader');
  if (!loader) return;
  window.addEventListener('load', () => {
    setTimeout(() => loader.classList.add('hidden'), 400);
  });
}

/* ─── Scroll Progress Bar ────────────────────────────────────────────────────── */
function initScrollProgress() {
  const bar = document.getElementById('scrollProgress');
  if (!bar) return;
  window.addEventListener('scroll', () => {
    const pct = (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100;
    bar.style.width = Math.min(100, pct) + '%';
  }, { passive: true });
}

/* ─── Lazy Image Fade ────────────────────────────────────────────────────────── */
function initLazyImages() {
  document.querySelectorAll('img[loading="lazy"]').forEach(img => {
    if (img.complete) img.classList.add('loaded');
    else img.addEventListener('load', () => img.classList.add('loaded'));
  });
}

/* ─── Keyboard nav for cart ──────────────────────────────────────────────────── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeCart();
});

/* ─── Format price helper ────────────────────────────────────────────────────── */
function formatPrice(amount) {
  return '₹' + parseFloat(amount).toLocaleString('en-IN');
}

/* ─── Sticky buy bar (mobile product page) ───────────────────────────────────── */
function initStickyBuyBar() {
  const bar = document.getElementById('stickyBuyBar');
  const actions = document.querySelector('.product-actions');
  if (!bar || !actions) return;
  const observer = new IntersectionObserver(entries => {
    bar.style.display = entries[0].isIntersecting ? 'none' : 'flex';
  }, { threshold: 0.1 });
  observer.observe(actions);
}

/* ─── Re-init on DOMContentLoaded ───────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initPageLoader();
  initScrollProgress();
  initLazyImages();
  initStickyBuyBar();
});
