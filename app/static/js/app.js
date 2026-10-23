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

  // ── ჯგუფური მონიშვნა (QC სია) ────────────────────────────────
  function syncBulk() {
    const form = document.getElementById('bulk-form');
    if (!form) return;
    const n = form.querySelectorAll('input[name=ids]:checked').length;
    const bar = document.getElementById('bulkbar');
    if (bar) { bar.hidden = n === 0; document.getElementById('bulk-n').textContent = n; }
  }
  document.addEventListener('change', function (e) {
    if (e.target.classList.contains('check-all')) {
      const form = e.target.closest('form');
      form.querySelectorAll('input[name=ids]:not(:disabled)').forEach(function (c) { c.checked = e.target.checked; });
    }
    if (e.target.name === 'ids' || e.target.classList.contains('check-all')) syncBulk();
  });
  document.body.addEventListener('htmx:afterSwap', syncBulk);

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
  function menu(open) {
    root.classList.toggle('rail-open', open);
    if (menuBtn) menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (scrim) scrim.hidden = !open;
  }
  if (menuBtn) menuBtn.addEventListener('click', function () { menu(!root.classList.contains('rail-open')); });
  if (scrim) scrim.addEventListener('click', function () { menu(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && root.classList.contains('rail-open')) menu(false); });

  const esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  const SVG = {
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    go: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>',
    board: '<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="11" rx="1.5"/><rect x="17" y="4" width="4" height="7" rx="1.5"/>',
    rows: '<path d="M3 6h18M3 12h18M3 18h18"/>'
  };
  function ico(n, s) { return '<svg class="ico-svg" width="' + (s || 16) + '" height="' + (s || 16) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + SVG[n] + '</svg>'; }

  // ── ბრძანებები და ოქმის ძებნა (Ctrl+K) ───────────────────────────
  // მხოლოდ არსებული გვერდები (მენიუდან, ანუ როლის უფლებით) და არსებული GET ფილტრები.
  function navLinks() {
    return Array.prototype.map.call(document.querySelectorAll('#rail .nav a.nav-item'), function (a) {
      return { t: a.textContent.trim(), href: a.getAttribute('href'), i: 'go', s: 'გვერდი' };
    });
  }
  function searchTargets(q) {
    const v = q.trim();
    if (!/^[\d.]{3,}$/.test(v)) return [];
    const key = v.indexOf('.') >= 0 ? 'cad' : 'protocol';
    const has = function (h) { return !!document.querySelector('#rail .nav a[href="' + h + '"]'); };
    const out = [];
    if (has('/qc')) [['todo', 'გასავლელში'], ['returned', 'უკან მობრუნებულში'], ['sent', 'გაგზავნილში'], ['closed', 'დასრულებულში']].forEach(function (t) {
      out.push({ t: (key === 'cad' ? 'საკ. კოდი ' : 'ოქმი ') + v, s: 'QC — ' + t[1], i: 'search', href: '/qc?tab=' + t[0] + '&' + key + '=' + encodeURIComponent(v) });
    });
    if (has('/field')) [['systematic', 'სისტემური'], ['sporadic', 'სპორადული'], ['manager', 'მენეჯერზე']].forEach(function (t) {
      out.push({ t: (key === 'cad' ? 'საკ. კოდი ' : 'ოქმი ') + v, s: 'ველი — ' + t[1], i: 'search', href: '/field?tab=' + t[0] + '&' + key + '=' + encodeURIComponent(v) });
    });
    return out;
  }
  function openCmdk() {
    if (document.querySelector('.cmdk')) return;
    const sc = document.createElement('div'); sc.className = 'scrim'; sc.style.zIndex = 94;
    const box = document.createElement('div');
    box.className = 'cmdk'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-label', 'ძებნა და გადასვლა');
    box.innerHTML = '<div class="cmdk-input">' + ico('search', 20) + '<input placeholder="ოქმის ნომერი, საკადასტრო კოდი ან გვერდი…" aria-label="ძებნა" autocomplete="off"></div>' +
      '<div class="cmdk-list" role="listbox"></div>' +
      '<div class="cmdk-foot"><span><span class="kbd">↑</span> <span class="kbd">↓</span> არჩევა</span><span><span class="kbd">Enter</span> გადასვლა</span><span><span class="kbd">Esc</span> დახურვა</span><span>ძებნა — არსებული ფილტრებით</span></div>';
    document.body.append(sc, box);
    const input = box.querySelector('input'), list = box.querySelector('.cmdk-list');
    const extra = [];
    const next = document.querySelector('a[href="/qc/next"]');
    if (next) extra.push({ t: 'შემდეგი ოქმი', s: 'QC რიგი', i: 'go', href: '/qc/next' });
    let rows = [], sel = 0;
    function draw() {
      const q = input.value.trim().toLowerCase();
      const found = searchTargets(q);
      const pages = extra.concat(navLinks()).filter(function (r) { return !q || r.t.toLowerCase().indexOf(q) >= 0; });
      rows = found.concat(pages);
      sel = Math.min(sel, Math.max(0, rows.length - 1));
      let h = '';
      rows.forEach(function (r, k) {
        if (k === 0 && found.length) h += '<div class="cmdk-label">ძებნა</div>';
        if (k === found.length) h += '<div class="cmdk-label">გვერდები</div>';
        h += '<button type="button" class="cmdk-row' + (k === sel ? ' on' : '') + '" role="option" aria-selected="' + (k === sel) + '" data-k="' + k + '">' + ico(r.i) + '<span>' + esc(r.t) + '</span><span class="sub">' + esc(r.s) + '</span></button>';
      });
      list.innerHTML = h || '<div class="cmdk-label">ვერაფერი მოიძებნა — ოქმისთვის ჩაწერეთ მინიმუმ 3 ციფრი</div>';
    }
    function close() { box.remove(); sc.remove(); document.removeEventListener('keydown', key, true); }
    function go(k) { const r = rows[k]; if (r) { close(); window.location = r.href; } }
    function key(e) {
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); sel = (sel + 1) % Math.max(1, rows.length); draw(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = (sel - 1 + rows.length) % Math.max(1, rows.length); draw(); }
      else if (e.key === 'Enter') { e.preventDefault(); go(sel); }
    }
    document.addEventListener('keydown', key, true);
    input.addEventListener('input', function () { sel = 0; draw(); });
    list.addEventListener('click', function (e) { const b = e.target.closest('[data-k]'); if (b) go(+b.dataset.k); });
    sc.addEventListener('click', close);
    draw(); input.focus();
  }
  const cmdkBtn = document.getElementById('cmdk-open');
  if (cmdkBtn) {
    cmdkBtn.addEventListener('click', openCmdk);
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openCmdk(); }
    });
  }

  // ── სწრაფი ნახვა: ოქმის ბარათი გვერდიდან გამოსულ პანელში ──────────
  // იკითხება იგივე /items/{id} გვერდი (GET — მონაცემი არ იცვლება, უფლებებს სერვერი ამოწმებს);
  // ფორმები პანელში არ ჩანს — მოქმედებისთვის „ბარათის გახსნა“.
  let drawerEl = null, drawerRow = null;
  function closeDrawer() {
    if (!drawerEl) return;
    const d = drawerEl, s = document.querySelector('.scrim.for-drawer');
    drawerEl = null; drawerRow = null;
    d.classList.add('leaving');
    setTimeout(function () { d.remove(); if (s) s.remove(); }, 200);
  }
  // მხოლოდ ხილული (ცხრილი ან დაფა — რომელიც ჩართულია), რომ ↑ ↓ ეკრანზე ნანახ რიგს მიჰყვეს
  function peekRows() { return Array.prototype.filter.call(document.querySelectorAll('[data-peek]'), function (b) { return b.offsetParent !== null || b === drawerRow; }); }
  function openPeek(btn) {
    const url = btn.dataset.peek;
    const row = btn.closest('tr, .b-card');
    const link = row && row.querySelector('a[href^="/items/"]');
    const full = link ? link.getAttribute('href') : url;
    if (!drawerEl) {
      const s = document.createElement('div'); s.className = 'scrim for-drawer'; s.addEventListener('click', closeDrawer);
      drawerEl = document.createElement('aside');
      drawerEl.className = 'drawer'; drawerEl.setAttribute('role', 'dialog'); drawerEl.setAttribute('aria-modal', 'true'); drawerEl.setAttribute('aria-label', 'ოქმის სწრაფი ნახვა');
      document.body.append(s, drawerEl);
    }
    drawerRow = btn;
    drawerEl.innerHTML = '<div class="drawer-head"><div class="grow"><div class="eyebrow">სწრაფი ნახვა</div><div class="skel" style="width:60%;height:22px"></div></div>' +
      '<button type="button" class="icon-btn" data-dclose aria-label="დახურვა">' + ico('x', 18) + '</button></div>' +
      '<div class="drawer-body"><div class="skel"></div><div class="skel" style="width:80%"></div><div class="skel" style="width:70%"></div><div class="skel"></div></div>' +
      '<div class="drawer-foot"><a class="btn btn-primary" href="' + esc(full) + '">ბარათის გახსნა</a>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-dmove="-1" aria-label="წინა">' + ico('up') + '</button><button type="button" class="btn btn-ghost btn-sm" data-dmove="1" aria-label="შემდეგი">' + ico('down') + '</button>' +
      '<span class="hint">↑ ↓ — სხვა ოქმი · Esc — დახურვა</span></div>';
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
        drawerEl.querySelector('.drawer-head .grow').innerHTML = '<div class="eyebrow">სწრაფი ნახვა</div><h2>' + esc(h1 ? h1.textContent.trim() : '') + '</h2>' +
          (cad ? cad.outerHTML : '') + (sub ? '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">' + sub.innerHTML + '</div>' : '');
        drawerEl.querySelector('.drawer-body').innerHTML = parts.join('') || '<div class="empty">ინფორმაცია ვერ მოიძებნა.</div>';
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
    if (e.key === 'Escape') { closeDrawer(); }
    else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      e.preventDefault();
      const all = peekRows(), i = all.indexOf(drawerRow), n = all[i + (e.key === 'ArrowDown' ? 1 : -1)];
      if (n) openPeek(n);
    }
  });

  // ── Board ხედი: მიმდინარე გვერდის ოქმები მდგომარეობის სვეტებად ──────
  // მონაცემი იგივეა, რაც ცხრილში (სერვერის მიერ გაფილტრული) — მხოლოდ განლაგება იცვლება.
  const COLS = {
    qc: [['gray', 'გასავლელი'], ['draft', 'შენახული — გასაგზავნი'], ['yellow', 'ველმა უპასუხა'], ['lightgreen', 'გაგზავნილია'], ['green', 'დასრულებული']],
    field: [['orange', 'პასუხი სჭირდება'], ['blue', 'მენეჯერთან'], ['lightgreen', 'QC-ს მხარეს'], ['green', 'დასრულებული']]
  };
  function cell(tr, label) {
    const td = Array.prototype.find.call(tr.children, function (c) { return c.dataset.label === label; });
    return td ? td.innerHTML.trim() : '';
  }
  // დაფა თავიდან სერვერის მიმდინარე გვერდს აჩვენებს; „შემდეგი გვერდის დამატება“ იმავე სიას
  // ითხოვს იმავე ფილტრებით (?page=N, HX-Request — სერვერი მხოლოდ ცხრილის ფრაგმენტს აბრუნებს).
  // შერჩევის, დალაგების და გვერდებად დაყოფის წესები სერვერზე რჩება.
  function boardCard(tr) {
    const m = /\br-(\w+)/.exec(tr.className);
    if (!m) return null;
    const id = tr.querySelector('td.mono');
    const html = '<div class="b-card c-' + m[1] + '" data-href="' + esc(tr.dataset.href || '') + '">' +
      '<div class="b-id">' + (id ? id.innerHTML : '') + '</div>' +
      '<div class="b-cad">' + cell(tr, 'საკ. კოდი') + '</div>' +
      '<div class="b-meta">' + cell(tr, 'ვერდიქტი') + ' ' + cell(tr, 'ველის პასუხი') + '</div>' +
      (cell(tr, 'კოდები') ? '<div class="b-meta">' + cell(tr, 'კოდები') + '</div>' : '') +
      '<div class="b-meta muted">' + cell(tr, 'ამზომველი').replace(/<br\s*\/?>/g, ', ') + '</div></div>';
    return { color: m[1], html: html.replace(/<input[^>]*>/g, '') };
  }
  function buildBoard(card) {
    const kind = card.dataset.board, table = card.querySelector('table.data');
    if (!table) return null;
    const total = +card.dataset.total || 0;
    const state = { page: +card.dataset.page || 1, pages: +card.dataset.pages || 1, shown: 0 };
    const b = document.createElement('div');
    b.className = 'board-wrap';
    b.innerHTML = '<div class="board-note"><span class="bn-text"></span><button type="button" class="btn btn-secondary btn-sm" data-board-more hidden>შემდეგი გვერდის დამატება</button></div>' +
      '<div class="board">' + COLS[kind].map(function (c) {
        return '<section class="b-col c-' + c[0] + '" data-col="' + c[0] + '"><div class="b-col-head"><i class="sw ' + c[0] + '"></i>' + c[1] + '<span class="n">0</span></div>' +
          '<div class="b-items"></div><div class="b-empty">ჩატვირთულ ოქმებში არ არის</div></section>';
      }).join('') + '</div>';
    const note = b.querySelector('.bn-text'), more = b.querySelector('[data-board-more]');
    function add(rows) {
      rows.forEach(function (tr) {
        const c = boardCard(tr);
        if (!c) return;
        const col = b.querySelector('[data-col="' + c.color + '"]');
        if (!col) return;
        col.querySelector('.b-items').insertAdjacentHTML('beforeend', c.html);
        state.shown++;
      });
      b.querySelectorAll('.b-col').forEach(function (col) {
        const n = col.querySelectorAll('.b-card').length;
        col.querySelector('.n').textContent = n;
        col.querySelector('.b-empty').hidden = n > 0;
      });
      note.innerHTML = 'დაფაზე ნაჩვენებია <b>' + state.shown + '</b> ოქმი <b>' + total + '</b>-დან (იგივე ფილტრი და რიგი, რაც ცხრილში)' +
        (state.page < state.pages ? ' · ჩატვირთულია ' + state.page + ' გვერდი ' + state.pages + '-დან' : '');
      more.hidden = state.page >= state.pages;
    }
    add(Array.prototype.slice.call(table.querySelectorAll('tbody tr')));
    more.addEventListener('click', function () {
      const u = new URL(window.location.href);
      u.searchParams.set('page', String(state.page + 1));
      more.disabled = true; more.textContent = 'იტვირთება…';
      fetch(u.pathname + u.search, { credentials: 'same-origin', headers: { 'HX-Request': 'true', Accept: 'text/html' } })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (html) {
          const doc = new DOMParser().parseFromString(html, 'text/html');
          const src = doc.querySelector('[data-board] table.data');
          state.page++;
          add(src ? Array.prototype.slice.call(src.querySelectorAll('tbody tr')) : []);
        })
        .catch(function (e) { note.insertAdjacentHTML('beforeend', ' · <span class="v-negative">ვერ ჩაიტვირთა (' + esc(e.message) + ')</span>'); })
        .finally(function () { more.disabled = false; more.textContent = 'შემდეგი გვერდის დამატება'; });
    });
    return b;
  }
  function initBoards() {
    document.querySelectorAll('[data-board]').forEach(function (card) {
      if (card.dataset.boardInit || !card.querySelector('table.data tbody tr')) return;
      card.dataset.boardInit = '1';
      const head = card.querySelector('.card-head');
      const wrap = card.querySelector('.table-wrap');
      if (!head || !wrap) return;
      const sw = document.createElement('div');
      sw.className = 'seg view-switch'; sw.setAttribute('role', 'group'); sw.setAttribute('aria-label', 'ხედი');
      sw.innerHTML = '<button type="button" data-view="table">' + ico('rows', 14) + 'ცხრილი</button><button type="button" data-view="board">' + ico('board', 14) + 'დაფა</button>';
      head.appendChild(sw);
      let board = null;
      function set(v) {
        if (v === 'board' && !board) { board = buildBoard(card); if (board) wrap.after(board); }
        wrap.hidden = v === 'board';
        if (board) board.hidden = v !== 'board';
        sw.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.view === v ? 'true' : 'false'); });
        store('qcp.view.' + card.dataset.board, v);
      }
      sw.addEventListener('click', function (e) { const b = e.target.closest('[data-view]'); if (b) set(b.dataset.view); });
      set(store('qcp.view.' + card.dataset.board) === 'board' ? 'board' : 'table');
    });
  }
  document.addEventListener('click', function (e) {
    const c = e.target.closest('.b-card[data-href]');
    if (c && !e.target.closest('a, button')) window.location = c.dataset.href;
  });
  initBoards();
  document.body.addEventListener('htmx:afterSwap', initBoards);

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
