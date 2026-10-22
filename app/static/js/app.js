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
})();
