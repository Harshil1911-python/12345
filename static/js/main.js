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

function imgUrl(imgId) {
  if (!imgId) return '';
  return '/pimg/' + imgId;
}

function addToCart(id, name, price, imgId, onlyOne) {
  const isOne = onlyOne === true || onlyOne === 'true';
  if (isOne) {
    if (!cart.find(i => i.id === id))
      cart.push({ id, name, price: parseFloat(price), imgId, qty: 1, onlyOne: true });
  } else {
    const existing = cart.find(i => i.id === id);
    if (existing) existing.qty += 1;
    else cart.push({ id, name, price: parseFloat(price), imgId, qty: 1, onlyOne: false });
  }
  saveCart();
  openCart();
  showToast(`${name} added to your selection`);
}

function removeFromCart(id) {
  cart = cart.filter(i => i.id !== id);
  saveCart();
}

function changeQty(id, delta) {
  const item = cart.find(i => i.id === id);
  if (item) { item.qty = Math.max(1, item.qty + delta); saveCart(); }
}

function renderCart() {
  const container = document.getElementById('cartItems');
  const totalEl   = document.getElementById('cartTotal');
  if (!container) return;

  if (cart.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:48px 20px;">
        <div style="width:56px;height:56px;border:1px solid var(--beige);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;color:var(--beige);">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/></svg>
        </div>
        <p style="font-size:.82rem;color:var(--gray-light);">Your selection is empty</p>
      </div>`;
    if (totalEl) totalEl.textContent = '₹0';
    return;
  }

  container.innerHTML = cart.map(item => `
    <div class="cart-item">
      <div class="cart-item-img" style="background:var(--cream);display:flex;align-items:center;justify-content:center;overflow:hidden;">
        ${item.imgId
          ? `<img src="${imgUrl(item.imgId)}" alt="${item.name}" style="width:100%;height:100%;object-fit:cover;"/>`
          : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="color:var(--beige)"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>`}
      </div>
      <div class="cart-item-info">
        <div class="cart-item-name">${item.name}</div>
        <div class="cart-item-price">₹${(item.price * item.qty).toLocaleString('en-IN')}</div>
        ${item.onlyOne
          ? `<div style="font-size:.58rem;letter-spacing:.12em;text-transform:uppercase;color:var(--champagne);margin-top:4px;">One of a kind</div>`
          : `<div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
               <button onclick="changeQty('${item.id}',-1)" style="width:22px;height:22px;border:1px solid var(--beige);background:none;cursor:pointer;font-size:.9rem;display:flex;align-items:center;justify-content:center;">−</button>
               <span style="font-size:.8rem;">${item.qty}</span>
               <button onclick="changeQty('${item.id}',1)" style="width:22px;height:22px;border:1px solid var(--beige);background:none;cursor:pointer;font-size:.9rem;display:flex;align-items:center;justify-content:center;">+</button>
             </div>`}
      </div>
      <button class="cart-item-remove" onclick="removeFromCart('${item.id}')">Remove</button>
    </div>`).join('');

  const total = cart.reduce((s, i) => s + i.price * i.qty, 0);
  if (totalEl) totalEl.textContent = '₹' + total.toLocaleString('en-IN');
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
  document.getElementById('cartDrawer')?.classList.contains('open') ? closeCart() : openCart();
}

/* ─── Toast ──────────────────────────────────────────────────────────────────── */
function showToast(message) {
  let toast = document.getElementById('henosisToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'henosisToast';
    toast.style.cssText = 'position:fixed;bottom:32px;left:50%;transform:translateX(-50%) translateY(20px);background:var(--charcoal);color:var(--ivory);padding:14px 28px;font-family:var(--font-body);font-size:.78rem;letter-spacing:.08em;z-index:9999;opacity:0;transition:all .4s cubic-bezier(.16,1,.3,1);pointer-events:none;white-space:nowrap;border-left:2px solid var(--gold);';
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

/* ─── Scroll Reveal ──────────────────────────────────────────────────────────── */
function initReveal() {
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
  }, { threshold: 0.1 });
  document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
}

/* ─── Nav scroll ─────────────────────────────────────────────────────────────── */
function initNav() {
  const nav = document.getElementById('nav');
  if (!nav) return;
  window.addEventListener('scroll', () => nav.classList.toggle('scrolled', window.scrollY > 40), { passive: true });
}

/* ─── Page Loader ────────────────────────────────────────────────────────────── */
function initPageLoader() {
  const loader = document.getElementById('pageLoader');
  if (!loader) return;
  window.addEventListener('load', () => setTimeout(() => loader.classList.add('hidden'), 300));
}

/* ─── Scroll Progress ────────────────────────────────────────────────────────── */
function initScrollProgress() {
  const bar = document.getElementById('scrollProgress');
  if (!bar) return;
  window.addEventListener('scroll', () => {
    bar.style.width = Math.min(100, (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100) + '%';
  }, { passive: true });
}

/* ─── Product Image Gallery ──────────────────────────────────────────────────── */
function initProductGallery() {
  const thumbs  = document.querySelectorAll('.product-thumb');
  const mainImg = document.getElementById('mainProductImage');
  if (!thumbs.length || !mainImg) return;
  thumbs.forEach(t => {
    t.addEventListener('click', () => {
      thumbs.forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      mainImg.style.opacity = '0';
      setTimeout(() => { mainImg.src = t.dataset.src; mainImg.style.opacity = '1'; }, 200);
    });
  });
  mainImg.style.transition = 'opacity .3s ease';
}

/* ─── Checkout summary ───────────────────────────────────────────────────────── */
function renderCheckoutSummary() {
  const container = document.getElementById('summaryItems');
  const totalEl   = document.getElementById('summaryTotal');
  if (!container) return;
  if (cart.length === 0) { container.innerHTML = '<p style="font-size:.85rem;color:var(--gray-mid);padding:12px 0;">No items in cart</p>'; return; }
  container.innerHTML = cart.map(item => `
    <div class="summary-item">
      <span class="summary-item-name">${item.name} <span style="color:var(--gray-light)">×${item.qty}</span></span>
      <span class="summary-item-price">₹${(item.price*item.qty).toLocaleString('en-IN')}</span>
    </div>`).join('');
  if (totalEl) totalEl.textContent = '₹' + cart.reduce((s,i)=>s+i.price*i.qty,0).toLocaleString('en-IN');
}

/* ─── Lazy images ────────────────────────────────────────────────────────────── */
function initLazyImages() {
  document.querySelectorAll('img[loading="lazy"]').forEach(img => {
    if (img.complete) img.classList.add('loaded');
    else img.addEventListener('load', () => img.classList.add('loaded'));
  });
}

/* ─── Keyboard ───────────────────────────────────────────────────────────────── */
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeCart(); });

/* ─── Init ───────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  updateCartCount();
  renderCart();
  initReveal();
  initNav();
  initPageLoader();
  initScrollProgress();
  initProductGallery();
  initLazyImages();
  renderCheckoutSummary();
});
