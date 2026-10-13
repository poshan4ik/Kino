/* АИС «Аврора» — UI core: toasts, drawer booking flow, seat map, helpers */
(function () {
  'use strict';

  /* ── Helpers ─────────────────────────────────────────── */
  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? decodeURIComponent(m.pop()) : '';
  }

  function formatPrice(amount) {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency', currency: 'RUB',
      minimumFractionDigits: 0, maximumFractionDigits: 0,
    }).format(amount);
  }

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function formatSessionDate(dateStr, timeStr) {
    var d = new Date(dateStr + 'T' + (timeStr || '00:00'));
    var today = new Date(); today.setHours(0, 0, 0, 0);
    var day = new Date(d); day.setHours(0, 0, 0, 0);
    var diff = Math.round((day - today) / 86400000);
    var time = timeStr ? timeStr.slice(0, 5) : '';
    var base;
    if (diff === 0) base = 'Сегодня';
    else if (diff === 1) base = 'Завтра';
    else base = d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    return base + (time ? ', ' + time : '');
  }

  function el(tag, cls, html) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html !== undefined) node.innerHTML = html;
    return node;
  }

  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── API ─────────────────────────────────────────────── */
  function apiError(payload, status) {
    var msg = 'Ошибка запроса';
    if (payload) {
      if (typeof payload === 'string') msg = payload;
      else if (payload.error) msg = payload.error;
      else if (payload.detail) msg = payload.detail;
      else {
        var parts = [];
        for (var k in payload) {
          if (Object.prototype.hasOwnProperty.call(payload, k)) {
            var v = payload[k];
            parts.push(Array.isArray(v) ? v.join(' ') : String(v));
          }
        }
        if (parts.length) msg = parts.join(' ');
      }
    }
    var err = new Error(msg);
    err.status = status;
    return err;
  }

  async function api(method, url, data) {
    var opts = {
      method: method,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    };
    if (data !== undefined) {
      opts.headers['X-CSRFToken'] = getCookie('csrftoken');
      if (typeof FormData !== 'undefined' && data instanceof FormData) {
        opts.body = data;
      } else {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(data);
      }
    } else if (method !== 'GET') {
      opts.headers['X-CSRFToken'] = getCookie('csrftoken');
    }
    var resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      throw new Error('Нет связи с сервером');
    }
    var payload = null;
    try { payload = await resp.json(); } catch (e) { /* пустой ответ */ }
    if (resp.status === 401 || resp.status === 403) {
      var err = apiError(payload, resp.status);
      err.auth = resp.status === 401 || (payload && String(payload.detail || '').indexOf('authenticated') !== -1);
      throw err;
    }
    if (!resp.ok) throw apiError(payload, resp.status);
    return payload;
  }

  /* ── Toasts ──────────────────────────────────────────── */
  var toastWrap = null;

  function toast(message, type) {
    type = type || 'info';
    if (!toastWrap) {
      toastWrap = el('div', 'toast-wrap');
      document.body.appendChild(toastWrap);
    }
    var icons = {
      success: '<svg class="toast-ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
      error: '<svg class="toast-ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
      info: '<svg class="toast-ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    };
    var node = el('div', 'toast ' + type);
    node.innerHTML = (icons[type] || icons.info) +
      '<span class="toast-msg">' + esc(message) + '</span>' +
      '<button class="toast-x" aria-label="Закрыть">&times;</button>';
    var remove = function () {
      node.classList.add('out');
      setTimeout(function () { node.remove(); }, 260);
    };
    node.querySelector('.toast-x').addEventListener('click', remove);
    toastWrap.appendChild(node);
    setTimeout(remove, 4500);
  }

  /* ── Header / mobile nav ─────────────────────────────── */
  function initHeader() {
    var header = document.querySelector('.site-header');
    if (header) {
      var onScroll = function () {
        header.classList.toggle('scrolled', window.scrollY > 8);
      };
      onScroll();
      window.addEventListener('scroll', onScroll, { passive: true });
    }
    var burger = document.getElementById('burgerBtn');
    var mobileNav = document.getElementById('mobileNav');
    if (burger && mobileNav) {
      burger.addEventListener('click', function () {
        var open = mobileNav.classList.toggle('open');
        burger.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }
  }

  /* ── Server messages → toasts ────────────────────────── */
  function initServerMessages() {
    document.querySelectorAll('[data-server-toast]').forEach(function (node) {
      toast(node.getAttribute('data-server-toast'), node.getAttribute('data-toast-type') || 'info');
      node.remove();
    });
  }

  /* ── Overlay / Drawer ────────────────────────────────── */
  var overlay = null;
  var drawer = null;
  var lastFocus = null;

  function ensureOverlay() {
    if (!overlay) {
      overlay = el('div', 'overlay');
      overlay.addEventListener('click', function () { closeDrawer(); });
      document.body.appendChild(overlay);
    }
    return overlay;
  }

  function ensureDrawer() {
    if (!drawer) {
      drawer = el('div', 'drawer');
      drawer.setAttribute('role', 'dialog');
      drawer.setAttribute('aria-modal', 'true');
      drawer.innerHTML =
        '<div class="drawer-head">' +
          '<div><h2 class="drawer-title" id="drawerTitle"></h2>' +
          '<p class="drawer-sub" id="drawerSub"></p></div>' +
          '<button class="drawer-close" id="drawerClose" aria-label="Закрыть">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
          '</button>' +
        '</div>' +
        '<div class="drawer-body" id="drawerBody"></div>' +
        '<div class="drawer-foot" id="drawerFoot"></div>';
      document.body.appendChild(drawer);
      drawer.querySelector('#drawerClose').addEventListener('click', function () { closeDrawer(); });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && drawer.classList.contains('open')) closeDrawer();
      });
    }
    return drawer;
  }

  function openDrawer() {
    lastFocus = document.activeElement;
    ensureOverlay().classList.add('open');
    ensureDrawer().classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer() {
    if (!drawer) return;
    drawer.classList.remove('open');
    if (overlay) overlay.classList.remove('open');
    document.body.style.overflow = '';
    if (booking.timer) { clearInterval(booking.timer); booking.timer = null; }
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    setTimeout(function () {
      if (drawer && !drawer.classList.contains('open')) {
        drawer.querySelector('#drawerBody').innerHTML = '';
        drawer.querySelector('#drawerFoot').innerHTML = '';
      }
    }, 340);
  }

  /* ── Seat map renderer ───────────────────────────────── */
  function renderSeatMap(container, layout, selected, onSelect) {
    container.innerHTML = '';
    var map = el('div', 'seat-map');
    Object.keys(layout).sort(function (a, b) {
      return parseInt(a.replace('row_', ''), 10) - parseInt(b.replace('row_', ''), 10);
    }).forEach(function (rowKey) {
      var seats = layout[rowKey];
      var rowNo = rowKey.replace('row_', '');
      var row = el('div', 'seat-row');
      row.appendChild(el('span', 'seat-row-num', esc(rowNo)));
      seats.forEach(function (seat) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'seat ' + seat.category + (seat.is_booked ? ' seat-taken' : '');
        if (selected && selected.has(seat.id)) btn.classList.add('seat-selected');
        btn.dataset.id = seat.id;
        btn.dataset.row = rowNo;
        btn.dataset.num = seat.number;
        btn.dataset.price = seat.price;
        btn.dataset.category = seat.category;
        btn.textContent = seat.number;
        btn.setAttribute('aria-label',
          'Ряд ' + rowNo + ', место ' + seat.number +
          (seat.is_booked ? ', занято' : ', ' + seat.price + ' ₽'));
        if (seat.is_booked) btn.disabled = true;
        else btn.addEventListener('click', function () { onSelect(seat, btn); });
        row.appendChild(btn);
      });
      map.appendChild(row);
    });
    container.appendChild(map);

    var legend = el('div', 'seat-legend');
    legend.innerHTML =
      '<span class="seat-legend-item"><span class="seat-legend-icon"></span>Свободно</span>' +
      '<span class="seat-legend-item" style="color:var(--accent-hover)"><span class="seat-legend-icon" style="background:var(--accent);border-color:var(--accent)"></span>Выбрано</span>' +
      '<span class="seat-legend-item" style="opacity:.5"><span class="seat-legend-icon" style="opacity:.5"></span>Занято</span>' +
      '<span class="seat-legend-item" style="color:var(--gold)"><span class="seat-legend-icon" style="border-color:var(--gold-45)"></span>Комфорт / VIP</span>';
    container.appendChild(legend);
  }

    var MAX_SEATS = 10;

  /* ── Booking drawer flow ─────────────────────────────── */
  var booking = {
    sessionId: null, session: null, layout: null,
    selected: new Map(), bookings: null, expiresAt: null,
    method: null, timer: null, opts: {},
  };

  function bookingReset() {
    booking.sessionId = null; booking.session = null; booking.layout = null;
    booking.selected = new Map(); booking.bookings = null;
    booking.expiresAt = null; booking.method = null;
    if (booking.timer) { clearInterval(booking.timer); booking.timer = null; }
  }

  function openBooking(sessionId, opts) {
    opts = opts || {};
    bookingReset();
    booking.sessionId = sessionId;
    booking.opts = opts;
    openDrawer();
    renderSeatsStep(true);
  }

  async function loadSessionData() {
    var results = await Promise.all([
      api('GET', '/api/sessions/' + booking.sessionId + '/'),
      api('GET', '/api/sessions/' + booking.sessionId + '/seats/'),
    ]);
    booking.session = results[0];
    booking.layout = results[1];
  }

  function drawerHead(title, sub) {
    document.getElementById('drawerTitle').textContent = title;
    document.getElementById('drawerSub').textContent = sub || '';
  }

  function sessionSub() {
    var s = booking.session;
    if (!s) return '';
    return formatSessionDate(s.date, s.time) +
      ' · Зал ' + s.hall_number + ' · ' + s.hall_type;
  }

  function selectedTotal() {
    var total = 0;
    booking.selected.forEach(function (seat) { total += seat.price; });
    return total;
  }

  function selectedChips() {
    var items = [];
    booking.selected.forEach(function (seat) {
      items.push({ row: seat.row, num: seat.number, price: seat.price });
    });
    items.sort(function (a, b) { return a.row - b.row || a.num - b.num; });
    return items;
  }

  function renderSummaryInto(node) {
    var chips = selectedChips();
    if (!chips.length) {
      node.innerHTML = '<p class="text-sm text-muted" style="margin:0">Выберите места на схеме — до ' + MAX_SEATS + '</p>';
      return;
    }
    var html = '';
    chips.forEach(function (c) {
      html += '<div class="summary-row"><span class="sum-place">Ряд ' + c.row + ', место ' + c.num +
        '</span><span class="sum-price">' + formatPrice(c.price) + '</span></div>';
    });
    html += '<div class="summary-total"><b>Итого</b><b>' + formatPrice(selectedTotal()) + '</b></div>';
    node.innerHTML = html;
  }

  function stepSeatsSkeleton() {
    var body = document.getElementById('drawerBody');
    var foot = document.getElementById('drawerFoot');
    body.innerHTML =
      '<div class="skeleton skeleton-line w40"></div>' +
      '<div class="skeleton" style="height:220px;margin-top:1rem"></div>' +
      '<div class="skeleton skeleton-line w60" style="margin-top:1rem"></div>';
    foot.innerHTML = '<div class="skeleton skeleton-line" style="margin:0"></div>';
  }

  async function renderSeatsStep(withLoad) {
    drawerHead('Выбор мест', withLoad ? 'Загрузка схемы зала…' : sessionSub());
    stepSeatsSkeleton();
    try {
      if (withLoad || !booking.session || !booking.layout) await loadSessionData();
    } catch (e) {
      if (e.status === 401 || e.auth) {
        window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname + window.location.search);
        return;
      }
      document.getElementById('drawerBody').innerHTML =
        '<div class="empty-state"><h3>Не удалось загрузить схему</h3><p>' + esc(e.message) + '</p></div>';
      document.getElementById('drawerFoot').innerHTML =
        '<button class="btn btn-outline w-full" id="bkRetry">Повторить</button>';
      document.getElementById('bkRetry').addEventListener('click', function () { renderSeatsStep(true); });
      return;
    }

    drawerHead(booking.session.movie_title, sessionSub());
    var body = document.getElementById('drawerBody');
    var foot = document.getElementById('drawerFoot');
    body.innerHTML = '';

    var screen = el('div', 'screen-indicator', '<span>ЭКРАН</span>');
    body.appendChild(screen);
    var mapBox = el('div', '');
    mapBox.style.overflowX = 'auto';
    body.appendChild(mapBox);

    var onSelect = function (seat, btn) {
      if (booking.selected.has(seat.id)) {
        booking.selected.delete(seat.id);
        btn.classList.remove('seat-selected');
      } else {
        if (booking.selected.size >= MAX_SEATS) {
          toast('Максимум ' + MAX_SEATS + ' мест за бронирование', 'error');
          return;
        }
        booking.selected.set(seat.id, {
          id: seat.id, row: parseInt(btn.dataset.row, 10),
          num: seat.number, price: seat.price, category: seat.category,
        });
        btn.classList.add('seat-selected');
      }
      renderSummaryInto(document.getElementById('bkSummary'));
      var sumNode = document.getElementById('bkSum');
      if (sumNode) sumNode.textContent = formatPrice(selectedTotal());
      document.getElementById('bkContinue').disabled = booking.selected.size === 0;
    };

    renderSeatMap(mapBox, booking.layout, booking.selected, onSelect);

    foot.innerHTML =
      '<div class="summary-box" id="bkSummary"></div>' +
      '<button class="btn btn-primary w-full" id="bkContinue" style="margin-top:.85rem" disabled>Забронировать · <span id="bkSum"></span></button>' +
      '<p class="text-xs text-muted text-center" style="margin:.6rem 0 0">Места удерживаются 15 минут после бронирования</p>';

    renderSummaryInto(document.getElementById('bkSummary'));
    document.getElementById('bkSum').textContent = formatPrice(selectedTotal());

    document.getElementById('bkContinue').addEventListener('click', function () {
      if (booking.selected.size) holdSeats();
    });
  }

  async function holdSeats() {
    var btn = document.getElementById('bkContinue');
    btn.disabled = true;
    btn.textContent = 'Бронируем…';
    try {
      var seatIds = Array.from(booking.selected.keys());
      var data = await api('POST', '/api/bookings/hold/', {
        session: booking.sessionId, seats: seatIds,
      });
      booking.bookings = data.bookings;
      booking.expiresAt = new Date(data.expires_at);
      renderPayStep();
    } catch (e) {
      if (e.status === 401 || e.auth) {
        window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname + window.location.search);
        return;
      }
      toast(e.message, 'error');
      booking.selected.clear();
      renderSeatsStep(true);
    }
  }

  function paymentMethods() {
    var opts = booking.opts || {};
    if (opts.methods && opts.methods.length) return opts.methods;
    return ['online', 'card'];
  }

  function methodName(m) {
    return { online: 'Карта онлайн', card: 'Карта', cash: 'Наличные' }[m] || m;
  }

  function methodIcon(m) {
    if (m === 'cash') {
      return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/></svg>';
    }
    if (m === 'online') {
      return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>';
    }
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/><line x1="6" y1="15" x2="10" y2="15"/></svg>';
  }

  function renderPayStep() {
    drawerHead('Оплата', sessionSub());
    var body = document.getElementById('drawerBody');
    var foot = document.getElementById('drawerFoot');
    var methods = paymentMethods();
    booking.method = methods[0];

    body.innerHTML =
      '<div class="summary-box" id="paySummary"></div>' +
      '<div style="margin-top:1.1rem">' +
        '<p class="eyebrow">Способ оплаты</p>' +
        '<div class="payment-methods" id="payMethods">' +
          methods.map(function (m, i) {
            return '<button type="button" class="method-chip' + (i === 0 ? ' active' : '') +
              '" data-method="' + m + '">' + methodIcon(m) + methodName(m) + '</button>';
          }).join('') +
        '</div>' +
      '</div>' +
      '<div class="panel p-4" style="margin-top:1.1rem;display:flex;align-items:center;justify-content:space-between;gap:.75rem">' +
        '<span class="text-sm text-muted">Время брони</span>' +
        '<span class="countdown" id="payCd"><span class="cd-dot"></span><span id="payCdText">15:00</span></span>' +
      '</div>';

    foot.innerHTML =
      '<button class="btn btn-primary w-full" id="payBtn">Оплатить ' + formatPrice(selectedTotal()) + '</button>' +
      '<button class="btn btn-ghost w-full" id="payBack" style="margin-top:.5rem">← Изменить места</button>';

    var chips = selectedChips();
    var html = '';
    chips.forEach(function (c) {
      html += '<div class="summary-row"><span class="sum-place">Ряд ' + c.row + ', место ' + c.num +
        '</span><span class="sum-price">' + formatPrice(c.price) + '</span></div>';
    });
    html += '<div class="summary-total"><b>К оплате</b><b>' + formatPrice(selectedTotal()) + '</b></div>';
    document.getElementById('paySummary').innerHTML = html;

    document.querySelectorAll('#payMethods .method-chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        document.querySelectorAll('#payMethods .method-chip').forEach(function (c) { c.classList.remove('active'); });
        chip.classList.add('active');
        booking.method = chip.dataset.method;
      });
    });

    startCountdown();
    document.getElementById('payBtn').addEventListener('click', payBookings);
    document.getElementById('payBack').addEventListener('click', function () {
      if (booking.timer) { clearInterval(booking.timer); booking.timer = null; }
      booking.selected.clear();
      renderSeatsStep(true);
    });
  }

  function startCountdown() {
    var text = document.getElementById('payCdText');
    var wrap = document.getElementById('payCd');
    var btn = document.getElementById('payBtn');
    if (booking.timer) clearInterval(booking.timer);

    function tick() {
      if (!document.body.contains(text)) { clearInterval(booking.timer); booking.timer = null; return; }
      var diff = booking.expiresAt - new Date();
      if (diff <= 0) {
        clearInterval(booking.timer); booking.timer = null;
        text.textContent = '00:00';
        wrap.classList.add('warn');
        btn.disabled = true;
        btn.textContent = 'Время истекло — выберите места заново';
        toast('Время удержания мест истекло', 'error');
        return;
      }
      var total = Math.floor(diff / 1000);
      var mm = Math.floor(total / 60);
      var ss = total % 60;
      text.textContent = pad(mm) + ':' + pad(ss);
      wrap.classList.toggle('warn', diff < 120000);
    }
    tick();
    booking.timer = setInterval(tick, 1000);
  }

  async function payBookings() {
    var btn = document.getElementById('payBtn');
    btn.disabled = true;
    btn.textContent = 'Проводим оплату…';
    try {
      var tickets = await api('POST', '/api/bookings/pay/', {
        booking_ids: booking.bookings.map(function (b) { return b.id; }),
        method: booking.method,
      });
      if (booking.timer) { clearInterval(booking.timer); booking.timer = null; }
      renderSuccessStep(tickets);
    } catch (e) {
      toast(e.message, 'error');
      btn.disabled = false;
      btn.textContent = 'Оплатить ' + formatPrice(selectedTotal());
    }
  }

  function renderSuccessStep(tickets) {
    var first = booking.bookings[0];
    var number = 'AUR-' + String(first.id).padStart(6, '0');
    var chips = selectedChips();

    var ticketHtml = tickets.map(function (t, i) {
      var seat = chips[i] || { row: '?', num: '?' };
      return '<div class="summary-row">' +
        '<span class="sum-place">Ряд ' + seat.row + ', место ' + seat.num + '</span>' +
        '<span class="sum-price">' + esc(t.barcode) + '</span></div>';
    }).join('');

    var modal = el('div', 'modal-overlay');
    modal.innerHTML =
      '<div class="modal-card">' +
        '<div class="success-ring">' +
          '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><polyline points="20 6 9 17 4 12"/></svg>' +
        '</div>' +
        '<h2 style="font-family:\'Bebas Neue\',sans-serif;font-size:2rem;margin:0;color:var(--text)">Бронь подтверждена</h2>' +
        '<p class="text-sm text-muted" style="margin:.5rem 0 0">' + esc(booking.session.movie_title) + ' · ' + esc(sessionSub()) + '</p>' +
        '<div class="booking-number">' + esc(number) + '</div>' +
        '<div class="summary-box" style="margin-top:1.25rem;text-align:left">' + ticketHtml +
          '<div class="summary-total"><b>Оплачено</b><b>' + formatPrice(selectedTotal()) + '</b></div>' +
        '</div>' +
        '<div class="flex gap-2" style="margin-top:1.5rem">' +
          '<a href="/profile/" class="btn btn-primary" style="flex:1">Мои билеты</a>' +
          '<button class="btn btn-outline" style="flex:1" data-close>Готово</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(modal);
    requestAnimationFrame(function () { modal.classList.add('open'); });

    var close = function () {
      modal.classList.remove('open');
      setTimeout(function () { modal.remove(); }, 300);
      closeDrawer();
      bookingReset();
    };
    modal.querySelector('[data-close]').addEventListener('click', close);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
  }

  /* ── Session pills → drawer ──────────────────────────── */
  function initSessionBooking() {
    document.addEventListener('click', function (e) {
      var pill = e.target.closest('[data-book-session]');
      if (!pill) return;
      e.preventDefault();
      var sessionId = pill.getAttribute('data-book-session');
      var authed = pill.getAttribute('data-auth') === '1';
      if (!authed) {
        window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname + window.location.search);
        return;
      }
      var opts = {};
      if (pill.getAttribute('data-methods')) {
        opts.methods = pill.getAttribute('data-methods').split(',');
      }
      openBooking(sessionId, opts);
    });
  }

  /* ── Favorites ───────────────────────────────────────── */
  function initFavorites() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.fav-btn');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      if (btn.dataset.auth !== '1') {
        window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname + window.location.search);
        return;
      }
      var movieId = btn.dataset.movie;
      var isFav = btn.classList.contains('active');
      api(isFav ? 'DELETE' : 'POST', '/api/favorites/' + movieId + '/')
        .then(function () {
          btn.classList.toggle('active', !isFav);
          btn.setAttribute('aria-pressed', String(!isFav));
          toast(isFav ? 'Удалено из избранного' : 'Добавлено в избранное', 'success');
        })
        .catch(function (err) {
          if (err.status === 401 || err.status === 403) {
            window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname + window.location.search);
          } else {
            toast(err.message, 'error');
          }
        });
    });
  }

  /* ── Film card schedule accordion ─────────────────────── */
  function initFilmDays() {
    var openCard = null;
    var openBtn = null;

    function restoreIcon(btn) {
      var label = btn.getAttribute('data-label') || '';
      btn.innerHTML =
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> ' +
        esc(label);
    }

    function close() {
      if (!openCard) return;
      openCard.classList.remove('days-open');
      var d = openCard.querySelector('.film-card-days');
      if (d) d.classList.remove('open');
      if (openBtn) {
        openBtn.setAttribute('aria-expanded', 'false');
        restoreIcon(openBtn);
      }
      openCard = null;
      openBtn = null;
    }

    document.addEventListener('click', function (e) {
      var toggle = e.target.closest('.film-days-toggle');
      if (toggle) {
        e.preventDefault();
        var card = toggle.closest('.film-card');
        var days = card && card.querySelector('.film-card-days');
        if (!days) return;
        var willOpen = openCard !== card;
        close();
        if (willOpen) {
          openCard = card;
          openBtn = toggle;
          card.classList.add('days-open');
          days.classList.add('open');
          toggle.setAttribute('aria-expanded', 'true');
          toggle.innerHTML =
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Скрыть';
        }
        return;
      }
      if (openCard && !e.target.closest('.film-card-days')) close();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });
  }

  /* ── Countdown (generic, [data-countdown]) ───────────── */
  function initCountdowns() {
    var nodes = document.querySelectorAll('[data-countdown]');
    if (!nodes.length) return;
    function update() {
      nodes.forEach(function (node) {
        var exp = new Date(node.getAttribute('data-countdown'));
        var diff = exp - new Date();
        if (diff <= 0) { node.textContent = 'истекло'; return; }
        var total = Math.floor(diff / 1000);
        node.textContent = pad(Math.floor(total / 60)) + ':' + pad(total % 60);
      });
    }
    update();
    setInterval(update, 1000);
  }

  /* ── QR codes (qrcodejs, если подключён) ─────────────── */
  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function renderQR(root) {
    if (typeof QRCode === 'undefined') return;
    (root || document).querySelectorAll('.ticket-qr[data-qr]:empty').forEach(function (node) {
      try {
        new QRCode(node, {
          text: node.getAttribute('data-qr'),
          width: 88, height: 88,
          colorDark: cssVar('--bg', '#0d0e12'),
          colorLight: cssVar('--white', '#ffffff'),
          correctLevel: QRCode.CorrectLevel.M,
        });
      } catch (e) { /* fallback: barcode виден рядом */ }
    });
  }

  /* ── Hero parallax ───────────────────────────────────── */
  function initHeroParallax() {
    var hero = document.querySelector('.hero');
    if (!hero) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var layers = hero.querySelectorAll('.hero-bg, .hero-glow');
    if (!layers.length) return;
    var ticking = false;
    var update = function () {
      ticking = false;
      var rect = hero.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) return;
      var offset = Math.min(Math.max(-rect.top * 0.18, -120), 120);
      layers.forEach(function (layer, i) {
        var depth = i === 0 ? 1 : 0.5;
        layer.style.transform = (layer.classList.contains('hero-glow') ? 'scale(1.18) ' : '') +
          'translate3d(0,' + (offset * depth).toFixed(1) + 'px,0)';
      });
    };
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  /* ── Scroll reveal (IntersectionObserver) ────────────── */
  function initReveal() {
    var nodes = document.querySelectorAll('.reveal');
    if (!nodes.length) return;
    if (!('IntersectionObserver' in window) ||
        window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      nodes.forEach(function (n) { n.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
    nodes.forEach(function (n) { io.observe(n); });
  }

  /* ── Trailer modal ───────────────────────────────────── */
  function youtubeId(url) {
    if (!url) return null;
    var m = String(url).match(/(?:youtu\.be\/|[?&]v=|\/embed\/|\/shorts\/|\/live\/)([A-Za-z0-9_-]{6,})/);
    return m ? m[1] : null;
  }

  function openTrailer(url, title) {
    var id = youtubeId(url);
    if (!id) {
      toast('Ссылка на трейлер не распознана', 'error');
      return;
    }
    var overlay = el('div', 'modal-overlay');
    overlay.innerHTML =
      '<div class="modal-card trailer-card" role="dialog" aria-modal="true" aria-label="Трейлер">' +
        '<button class="trailer-close" type="button" aria-label="Закрыть трейлер">✕</button>' +
        '<div class="trailer-frame">' +
          '<iframe src="https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&rel=0" ' +
            'title="Трейлер" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>' +
        '</div>' +
        '<div class="trailer-caption"><span>' + esc(title || 'Трейлер') + '</span>' +
          '<span class="text-xs" style="opacity:.6;">Esc — закрыть</span></div>' +
      '</div>';
    document.body.appendChild(overlay);
    requestAnimationFrame(function () { overlay.classList.add('open'); });

    var closed = false;
    var close = function () {
      if (closed) return;
      closed = true;
      overlay.classList.remove('open');
      setTimeout(function () { overlay.remove(); }, 320);
      document.removeEventListener('keydown', onKey);
    };
    var onKey = function (e) { if (e.key === 'Escape') close(); };
    overlay.querySelector('.trailer-close').addEventListener('click', close);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    document.addEventListener('keydown', onKey);
  }

  function initTrailer() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-trailer]');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      openTrailer(btn.getAttribute('data-trailer'), btn.getAttribute('data-trailer-title'));
    });
  }

  /* ── Global error boundary for fetch buttons ─────────── */
  function guard(fn) {
    return function (e) {
      Promise.resolve(fn.call(this, e)).catch(function (err) {
        toast(err.message || 'Произошла ошибка', 'error');
      });
    };
  }

  /* ── Init ────────────────────────────────────────────── */
  function init() {
    initHeader();
    initServerMessages();
    initSessionBooking();
    initFavorites();
    initFilmDays();
    initCountdowns();
    initHeroParallax();
    initReveal();
    initTrailer();
    renderQR(document);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.Aurora = {
    api: api,
    toast: toast,
    getCookie: getCookie,
    formatPrice: formatPrice,
    formatSessionDate: formatSessionDate,
    openBooking: openBooking,
    openTrailer: openTrailer,
    closeDrawer: closeDrawer,
    renderSeatMap: renderSeatMap,
    renderQR: renderQR,
    esc: esc,
    guard: guard,
    cssVar: cssVar,
    MAX_SEATS: MAX_SEATS,
  };
})();
