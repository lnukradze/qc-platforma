/* NAPR QC — ინტერფეისის მცირე დამხმარეები (ჩარჩოს გარეშე). */
(function () {
  'use strict';

  // ── მწკრივზე დაწკაპუნება → ბარათი ─────────────────────────────
  document.addEventListener('click', function (e) {
    const tr = e.target.closest('tr[data-href]');
    if (!tr) return;
    if (e.target.closest('a, button, input, select, label, textarea')) return;
    if (e.ctrlKey || e.metaKey) { window.open(tr.dataset.href, '_blank'); return; }
    window.location = tr.dataset.href;
  });

  // ── დადასტურება საშიშ მოქმედებაზე ─────────────────────────────
  document.addEventListener('click', function (e) {
    const b = e.target.closest('[data-confirm]');
    if (b && !window.confirm(b.dataset.confirm)) { e.preventDefault(); }
  });

  // ── ფილტრები ტელეფონზე ჩაკეცილია (ღილაკი CSS-ით მხოლოდ ვიწრო ეკრანზე ჩანს) ──
  function initFilterToggles() {
    document.querySelectorAll('form.filters').forEach(function (f) {
      if (f.dataset.toggle) return;
      f.dataset.toggle = '1';
      const active = Array.prototype.filter.call(
        f.querySelectorAll('input:not([type=hidden]):not([type=checkbox]), select:not([data-nocount])'),
        function (e) { return e.value; }).length;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-ghost filters-toggle';
      b.setAttribute('aria-expanded', 'false');
      b.textContent = 'ფილტრები' + (active ? ' · ' + active + ' აქტიური' : '');
      b.addEventListener('click', function () {
        const open = f.classList.toggle('open');
        b.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      f.parentNode.insertBefore(b, f);
    });
  }
  initFilterToggles();

  // ── სიების ფილტრი (T-012 ბ): მენეჯერი / ამზომველი, სექტორი, თარიღები ──
  // ველში სახელი ჩანს, სერვერს კი ფარული ველით მიდის: სიიდან არჩეული — id, ხელით ჩაწერილი — ტექსტი
  // (ციფრებს სერვერი id-ად კითხულობს, T-011). JS-ის გარეშე ველი თავად იგზავნება სახელით.
  function initListFilters() {
    const f = document.querySelector('form.filters-lines');
    if (!f) return;
    function picker(key) {
      const vis = f.querySelector('#f-' + key), list = document.getElementById('dl-' + key);
      if (!vis || !list) return null;
      const hid = document.createElement('input');
      hid.type = 'hidden'; hid.name = key; hid.value = vis.dataset.pick || '';
      vis.removeAttribute('name');
      vis.after(hid);
      const p = { vis: vis, list: list, hid: hid, initial: list.innerHTML };
      p.resolve = function () {
        const t = vis.value.trim();
        const hits = Array.prototype.filter.call(list.options, function (o) { return o.value === t; });
        hid.value = hits.length === 1 ? hits[0].dataset.id : t;   // ერთნაირი სახელი ორჯერ → ტექსტით
      };
      vis.addEventListener('input', function () { p.resolve(); vis.dispatchEvent(new Event('pick')); });
      return p;
    }
    const mgr = picker('manager'), surv = picker('surveyor');
    if (mgr && surv) {
      let seq = 0, last = mgr.hid.value;
      mgr.vis.addEventListener('pick', function () {
        const id = mgr.hid.value;
        if (id === last) return;
        last = id;
        const n = ++seq;
        function fill(html) { if (n !== seq) return; surv.list.innerHTML = html; surv.resolve(); }
        if (!/^\d+$/.test(id)) { fill(surv.initial); return; }
        fetch('/api/filters/surveyors?manager=' + encodeURIComponent(id), { headers: { Accept: 'application/json' } })
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (rows) {
            if (!rows.length) { fill(surv.initial); return; }   // სხვისი გუნდი / უცნობი — სერვერის სია რჩება
            const box = document.createElement('datalist');
            rows.forEach(function (s) {
              const o = document.createElement('option');
              o.value = s.name; o.dataset.id = s.id;
              box.appendChild(o);
            });
            fill(box.innerHTML);
          })
          .catch(function () { fill(surv.initial); });
      });
    }
    const zone = f.querySelector('#f-zone'), sector = f.querySelector('#f-sector');
    if (zone && sector) {
      zone.addEventListener('input', function () {
        const on = !!zone.value.trim();
        sector.disabled = !on;
        sector.placeholder = on ? 'მაგ. 39' : 'ჯერ — ზონა';
      });
    }
    const from = f.querySelector('#f-df'), to = f.querySelector('#f-dt'), warn = f.querySelector('#f-range');
    if (from && to && warn) {
      const check = function () { warn.hidden = !(from.value && to.value && from.value >= to.value); };
      from.addEventListener('change', check);
      to.addEventListener('change', check);
    }
  }
  initListFilters();

  // ── ხარვეზის კოდები: ავტომატური შეთავაზება კომენტარიდან ─────────
  function initCodes() {
    const box = document.getElementById('codebox');
    const ta = document.querySelector('textarea[data-classify]');
    const input = document.getElementById('codes-input');
    const add = document.getElementById('code-add');
    const autoBtn = document.getElementById('code-auto');
    if (!box || !ta || !input) return;
    const sev = {};
    if (add) Array.from(add.options).forEach(function (o) { if (o.value) sev[o.value] = o.dataset.sev; });
    let manual = box.dataset.manual === '1';
    let touched = false;                       // მომხმარებელმა კოდები შეცვალა
    let codes = (box.dataset.initial || '').split(',').filter(Boolean);
    const src = document.createElement('input');
    src.type = 'hidden'; src.name = 'codes_source';
    input.after(src);

    function verdict() {
      const v = document.querySelector('input[name=verdict]:checked');
      return v ? v.value : '';
    }
    function render() {
      box.innerHTML = '';
      if (verdict() === 'positive') {
        box.innerHTML = '<span class="suggest">დადებით ვერდიქტზე კოდი არ ენიჭება.</span>';
        input.value = ''; src.value = 'auto';
        return;
      }
      if (!codes.length) {
        box.innerHTML = '<span class="suggest">კოდი ჯერ არ არის — დაწერეთ კომენტარი ან დაამატეთ ხელით.</span>';
      }
      codes.forEach(function (c) {
        const s = document.createElement('span');
        s.className = 'code sev-' + (sev[c] || '');
        s.textContent = c;
        const x = document.createElement('button');
        x.type = 'button'; x.textContent = '×'; x.title = 'მოხსნა';
        x.addEventListener('click', function () { codes = codes.filter(function (k) { return k !== c; }); manual = true; touched = true; render(); });
        s.appendChild(x);
        box.appendChild(s);
      });
      const tag = document.createElement('span');
      tag.className = 'suggest';
      tag.textContent = manual ? (box.dataset.source === 'legacy' && !touched ? ' · ძველი ცხრილიდან' : ' · ხელით შეცვლილი') : ' · ავტომატური';
      if (codes.length) box.appendChild(tag);
      input.value = codes.join(',');
      src.value = manual ? (touched ? 'manual' : (box.dataset.source || 'manual')) : 'auto';
    }
    function auto() {
      if (typeof window.classify !== 'function') return;
      codes = window.classify(ta.value);
      if (!ta.value.trim()) codes = [];
    }
    ta.addEventListener('input', function () { if (!manual) { auto(); render(); } });
    document.querySelectorAll('input[name=verdict]').forEach(function (r) { r.addEventListener('change', render); });
    if (add) add.addEventListener('change', function () {
      if (add.value && codes.indexOf(add.value) < 0) { codes.push(add.value); codes.sort(); manual = true; touched = true; render(); }
      add.value = '';
    });
    if (autoBtn) autoBtn.addEventListener('click', function () { manual = false; touched = true; auto(); render(); });
    if (!codes.length && ta.value.trim() && !manual) auto();
    render();
  }
  // DOMContentLoaded — ყველა სკრიპტის (მათ შორის qc-rules.js-ის) შესრულების შემდეგ
  document.addEventListener('DOMContentLoaded', initCodes);

  // ── ჩარჩო: თემა, მენიუს აკეცვა, ტელეფონზე მენიუ ─────────────────
  // არჩევანი მხოლოდ ამ ბრაუზერში ინახება (localStorage); სერვერზე არაფერი იგზავნება.
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  const root = document.documentElement;

  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', function () {
    const dark = root.dataset.theme !== 'dark';
    root.dataset.theme = dark ? 'dark' : 'light';
    store('qcp.theme', root.dataset.theme);
    document.dispatchEvent(new CustomEvent('qcp:theme'));
  });

  const collapse = document.getElementById('rail-collapse');
  if (collapse) collapse.addEventListener('click', function () {
    const on = root.classList.toggle('rail-collapsed');
    store('qcp.rail', on ? '1' : '0');
    setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 450);   // დიაგრამები სიგანეს მიჰყვეს
  });

  const menuBtn = document.getElementById('menu-toggle');
  const scrim = document.getElementById('rail-scrim');
  const rail = document.getElementById('rail');
  const mainCol = document.querySelector('.app > .main');
  const mobile = window.matchMedia('(max-width: 760px)');
  // ტელეფონზე დახურული მენიუ ეკრანს მიღმაა — inert, რომ Tab უხილავ ბმულებზე არ გადავიდეს;
  // გახსნილისას კი პირიქით — ფონი მიუწვდომელია, ფოკუსი მენიუში რჩება (U-17)
  function syncRail() {
    const open = root.classList.contains('rail-open');
    if (rail) rail.inert = mobile.matches && !open;
    if (mainCol) mainCol.inert = mobile.matches && open;
  }
  function menu(open, refocus) {
    root.classList.toggle('rail-open', open);
    if (menuBtn) menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (scrim) scrim.hidden = !open;
    syncRail();
    if (open && rail) { const first = rail.querySelector('.nav a[href]'); if (first) first.focus(); }
    else if (!open && refocus !== false && menuBtn) menuBtn.focus();
  }
  syncRail();
  mobile.addEventListener('change', function () {
    if (!mobile.matches && root.classList.contains('rail-open')) menu(false, false);
    syncRail();
  });
  if (menuBtn) menuBtn.addEventListener('click', function () { menu(!root.classList.contains('rail-open')); });
  if (scrim) scrim.addEventListener('click', function () { menu(false); });
  document.addEventListener('keydown', function (e) {
    if (!root.classList.contains('rail-open') || !mobile.matches) return;
    if (e.key === 'Escape') menu(false);
    else if (e.key === 'Tab' && rail) {
      const f = focusables(rail), i = f.indexOf(document.activeElement);
      if (!f.length) return;
      if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && (i < 0 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); }
    }
  });

  const esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  const SVG = {
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>'
  };
  function ico(n, s) { return '<svg class="ico-svg" width="' + (s || 16) + '" height="' + (s || 16) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + SVG[n] + '</svg>'; }

  // ── სწრაფი ნახვა: ოქმის ბარათი გვერდიდან გამოსულ პანელში ──────────
  // იკითხება იგივე /items/{id} გვერდი (GET — მონაცემი არ იცვლება, უფლებებს სერვერი ამოწმებს);
  // ფორმები პანელში არ ჩანს — მოქმედებისთვის „ბარათის გახსნა“.
  // დიალოგია (U-18): გახსნისას ფოკუსი შიგნით, Tab შიგნით ტრიალებს, ფონი (#app) inert-ია;
  // დახურვისას ფოკუსი ბრუნდება იმ რიგის ღილაკზე, რომლის ბარათიც ჩანდა.
  let drawerEl = null, drawerRow = null;
  const appEl = document.getElementById('app');
  function focusables(el) {
    return Array.prototype.filter.call(el.querySelectorAll('a[href], button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'),
      function (n) { return n.getClientRects().length > 0 && getComputedStyle(n).visibility !== 'hidden'; });
  }
  function closeDrawer() {
    if (!drawerEl) return;
    const d = drawerEl, s = document.querySelector('.scrim.for-drawer'), back = drawerRow;
    drawerEl = null; drawerRow = null;
    if (appEl) appEl.inert = false;
    d.classList.add('leaving');
    setTimeout(function () { d.remove(); if (s) s.remove(); }, 200);
    // HTMX-მა რიგი თუ ჩაანაცვლა — იგივე ოქმის ახალი ღილაკი; თუ აღარ არის — მთავარი შიგთავსი
    let t = back && back.isConnected && back.getClientRects().length ? back : null;
    if (!t && back) t = document.querySelector('[data-peek="' + CSS.escape(back.dataset.peek) + '"]');
    (t || document.getElementById('main')).focus();
  }
  // მხოლოდ ხილული, რომ ↑ ↓ ეკრანზე ნანახ რიგს მიჰყვეს
  function peekRows() { return Array.prototype.filter.call(document.querySelectorAll('[data-peek]'), function (b) { return b.offsetParent !== null || b === drawerRow; }); }
  function openPeek(btn) {
    const url = btn.dataset.peek;
    const row = btn.closest('tr');
    const link = row && row.querySelector('a[href^="/items/"]');
    const full = link ? link.getAttribute('href') : url;
    if (!drawerEl) {
      const s = document.createElement('div'); s.className = 'scrim for-drawer'; s.addEventListener('click', closeDrawer);
      drawerEl = document.createElement('aside');
      drawerEl.className = 'drawer'; drawerEl.setAttribute('role', 'dialog'); drawerEl.setAttribute('aria-modal', 'true'); drawerEl.setAttribute('aria-labelledby', 'drawer-title');
      document.body.append(s, drawerEl);
      if (appEl) appEl.inert = true;
    }
    // წინა / შემდეგი ღილაკით გადასვლისას ფოკუსი იმავე ღილაკზე რჩება, სხვა შემთხვევაში — „დახურვაზე“
    const ae = document.activeElement;
    const keep = ae && drawerEl.contains(ae) && ae.dataset.dmove;
    drawerRow = btn;
    drawerEl.innerHTML = '<div class="drawer-head"><div class="grow"><div class="eyebrow" id="drawer-title">სწრაფი ნახვა</div><div class="skel" style="width:60%;height:22px"></div></div>' +
      '<button type="button" class="icon-btn" data-dclose aria-label="დახურვა">' + ico('x', 18) + '</button></div>' +
      '<div class="drawer-body"><div class="skel"></div><div class="skel" style="width:80%"></div><div class="skel" style="width:70%"></div><div class="skel"></div></div>' +
      '<div class="drawer-foot"><a class="btn btn-primary" href="' + esc(full) + '">ბარათის გახსნა</a>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dmove="-1" aria-label="წინა">' + ico('up') + '</button><button type="button" class="btn btn-ghost btn-sm" data-dmove="1" aria-label="შემდეგი">' + ico('down') + '</button>' +
      '<span class="hint">↑ ↓ — სხვა ოქმი · Esc — დახურვა</span></div>';
    drawerEl.querySelector(keep ? '[data-dmove="' + keep + '"]' : '[data-dclose]').focus();
    fetch(url, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (!drawerEl || drawerRow !== btn) return;
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const head = doc.querySelector('.page-head');
        const h1 = head && head.querySelector('h1');
        const cad = head && head.querySelector('.ws-cad');
        const sub = head && head.querySelector('.sub');
        const parts = [];
        ['.stepper', '.resp-banner'].forEach(function (q) { const n = doc.querySelector(q); if (n) parts.push(n.outerHTML); });
        doc.querySelectorAll('.split > div:first-child > .card').forEach(function (c) {
          if (c.querySelector('.kv, .quote') && !c.querySelector('form#review-form:not(details form)')) parts.push(c.outerHTML);
        });
        const tl = doc.querySelector('.timeline');
        if (tl) { tl.querySelectorAll('li:nth-child(n+6)').forEach(function (li) { li.remove(); }); parts.push('<div class="card"><div class="card-head"><h2>ისტორია</h2><span class="muted small">ბოლო 5</span></div><div class="card-body">' + tl.outerHTML + '</div></div>'); }
        const lost = drawerEl.contains(document.activeElement) && drawerEl.querySelector('.drawer-body').contains(document.activeElement);
        drawerEl.querySelector('.drawer-head .grow').innerHTML = '<div class="eyebrow">სწრაფი ნახვა</div><h2 id="drawer-title">' + esc(h1 ? h1.textContent.trim() : '') + '</h2>' +
          (cad ? cad.outerHTML : '') + (sub ? '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">' + sub.innerHTML + '</div>' : '');
        drawerEl.querySelector('.drawer-body').innerHTML = parts.join('') || '<div class="empty">ინფორმაცია ვერ მოიძებნა.</div>';
        if (lost) drawerEl.querySelector('[data-dclose]').focus();
      })
      .catch(function (e) {
        if (drawerEl) drawerEl.querySelector('.drawer-body').innerHTML = '<div class="notice err">ბარათი ვერ ჩაიტვირთა (' + esc(e.message) + ').</div>';
      });
  }
  document.addEventListener('click', function (e) {
    const p = e.target.closest('[data-peek]');
    if (p) { e.preventDefault(); e.stopPropagation(); openPeek(p); return; }
    if (e.target.closest('[data-dclose]')) { closeDrawer(); return; }
    const m = e.target.closest('[data-dmove]');
    if (m && drawerRow) {
      const all = peekRows(), i = all.indexOf(drawerRow), n = all[i + (+m.dataset.dmove)];
      if (n) openPeek(n);
    }
  }, true);
  document.addEventListener('keydown', function (e) {
    if (!drawerEl) return;
    if (e.key === 'Escape') { e.stopImmediatePropagation(); closeDrawer(); }   // მხოლოდ ზედა დიალოგი იხურება
    else if (e.key === 'Tab') {
      const f = focusables(drawerEl), i = f.indexOf(document.activeElement);
      if (!f.length) { e.preventDefault(); return; }
      if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && (i < 0 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); }
    }
    else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      e.preventDefault();
      const all = peekRows(), i = all.indexOf(drawerRow), n = all[i + (e.key === 'ArrowDown' ? 1 : -1)];
      if (n) openPeek(n);
    }
  }, true);

  // ── ზონის მინი-რუკა (GIS): ყველა ზონა ნაცრისფრად, ოქმის ზონა — აქცენტით ──
  // წყარო: /static/geo/zones.geojson (იგივე, რასაც სტატისტიკის რუკა იყენებს).
  function drawZoneMap(el) {
    const zone = el.dataset.zone;
    fetch('/static/geo/zones.geojson').then(function (r) { return r.json(); }).then(function (g) {
      let x0 = 180, x1 = -180, y0 = 90, y1 = -90;
      const each = function (geom, fn) {
        const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.type === 'MultiPolygon' ? geom.coordinates : [];
        polys.forEach(function (p) { p.forEach(function (ring) { fn(ring); }); });
      };
      g.features.forEach(function (f) { each(f.geometry, function (ring) { ring.forEach(function (pt) {
        if (pt[0] < x0) x0 = pt[0]; if (pt[0] > x1) x1 = pt[0]; if (pt[1] < y0) y0 = pt[1]; if (pt[1] > y1) y1 = pt[1]; }); }); });
      const k = Math.cos((y0 + y1) / 2 * Math.PI / 180), W = 600, sc = W / ((x1 - x0) * k), H = (y1 - y0) * sc;
      const P = function (pt) { return ((pt[0] - x0) * k * sc).toFixed(1) + ',' + ((y1 - pt[1]) * sc).toFixed(1); };
      let paths = '', hi = '', cx = 0, cy = 0, n = 0, name = '';
      g.features.forEach(function (f) {
        let d = '';
        each(f.geometry, function (ring) { d += 'M' + ring.map(P).join('L') + 'Z'; });
        const on = String(f.properties.id) === zone;
        if (on) {
          name = f.properties.name || '';
          each(f.geometry, function (ring) { ring.forEach(function (pt) { const q = P(pt).split(','); cx += +q[0]; cy += +q[1]; n++; }); });
          hi = '<path d="' + d + '" fill="var(--accent)" fill-opacity=".85" stroke="var(--card)" stroke-width="1.2"><title>' + esc(zone + ' — ' + name) + '</title></path>';
        } else paths += '<path d="' + d + '"/>';
      });
      const pin = n ? '<circle cx="' + (cx / n).toFixed(1) + '" cy="' + (cy / n).toFixed(1) + '" r="14" fill="none" stroke="var(--accent)" stroke-width="1.5" opacity=".5"><animate attributeName="r" values="8;22;8" dur="2.6s" repeatCount="indefinite"/><animate attributeName="opacity" values=".7;0;.7" dur="2.6s" repeatCount="indefinite"/></circle>' : '';
      el.innerHTML = '<svg viewBox="-6 -6 ' + (W + 12) + ' ' + (H + 12).toFixed(0) + '" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">' +
        '<g fill="var(--sunk)" stroke="var(--border-strong)" stroke-width=".6">' + paths + '</g>' + hi + pin + '</svg>';
      if (!n) el.insertAdjacentHTML('beforeend', '<div class="hint">ზონა ' + esc(zone) + ' რუკაზე ვერ მოიძებნა.</div>');
    }).catch(function () { el.innerHTML = '<div class="hint">რუკა ვერ ჩაიტვირთა.</div>'; });
  }
  document.querySelectorAll('.zone-map[data-zone]').forEach(drawZoneMap);
})();
