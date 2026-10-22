/* სტატისტიკა — ფილტრები ერთ რიგში, ყველა დიაგრამა ერთსა და იმავე ჭრილზე.
   ფერები დალტონიზმის სიმულაციით გადამოწმებულია (dataviz validator):
   დადებითი #1baf7a · რეკომენდაცია #eda100 · უარყოფითი #d03b3b — ყოველ დიაგრამას
   ცხრილი ახლავს (ფერი მარტო მნიშვნელობას არ ატარებს). */
(function () {
  'use strict';
  const C = {
    pos: '#1baf7a', rec: '#eda100', neg: '#d03b3b', series: '#2a78d6',
    ink: '#1d2530', ink2: '#52514e', muted: '#66727f', grid: '#e7ebf0', axis: '#c3cbd6',
    surface: '#ffffff', ramp: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'],
  };
  const FONT = '"Noto Sans Georgian", "Segoe UI", system-ui, sans-serif';
  const fmt = (n) => (n === null || n === undefined) ? '—' :
    (Number.isInteger(n) ? n.toLocaleString('en-US').replace(/,/g, ' ') : (Math.round(n * 10) / 10).toString());
  const pct = (n) => (n === null || n === undefined) ? '—' : `${fmt(n)}%`;
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const charts = {};
  let zonesGeo = null;
  let last = null;

  function chart(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (!charts[id] || charts[id].getDom() !== el) charts[id] = echarts.init(el, null, { renderer: 'canvas' });
    return charts[id];
  }
  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c && c.resize()));

  const base = () => ({
    aria: { enabled: true },
    textStyle: { fontFamily: FONT, color: C.ink, fontSize: 12 },
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: { backgroundColor: '#fff', borderColor: C.axis, textStyle: { color: C.ink, fontFamily: FONT } },
  });
  const axisCommon = {
    axisLine: { lineStyle: { color: C.axis } }, axisTick: { show: false },
    axisLabel: { color: C.muted, fontFamily: FONT },
    splitLine: { lineStyle: { color: C.grid, type: 'solid' } },
  };

  // ── ფილტრები ──────────────────────────────────────────────────
  const form = document.getElementById('stats-filters');
  const range = document.getElementById('s-range');
  const dFrom = document.getElementById('s-from');
  const dTo = document.getElementById('s-to');
  const iso = (d) => d.toISOString().slice(0, 10);

  function applyRange() {
    const v = range.value;
    const today = new Date();
    if (v === 'all') { dFrom.value = ''; dTo.value = ''; }
    else if (/^\d+$/.test(v)) { const f = new Date(today); f.setDate(f.getDate() - Number(v) + 1); dFrom.value = iso(f); dTo.value = iso(today); }
    else if (v === 'year') { dFrom.value = `${today.getFullYear()}-01-01`; dTo.value = iso(today); }
    else if (v.startsWith('m')) { const o = range.selectedOptions[0]; dFrom.value = o.dataset.from; dTo.value = o.dataset.to; }
  }
  range.addEventListener('change', () => { applyRange(); if (range.value !== 'custom') load(); });
  [dFrom, dTo].forEach((i) => i.addEventListener('change', () => { range.value = 'custom'; }));
  form.addEventListener('submit', (e) => { e.preventDefault(); load(); });
  form.addEventListener('reset', () => setTimeout(() => { range.value = 'all'; applyRange(); load(); }, 0));
  form.querySelectorAll('select:not(#s-range)').forEach((s) => s.addEventListener('change', load));

  function params() {
    const p = new URLSearchParams();
    new FormData(form).forEach((v, k) => { if (k !== 'range' && v) p.set(k, v); });
    return p;
  }
  function restore() {
    const q = new URLSearchParams(location.search);
    q.forEach((v, k) => { const el = form.elements[k]; if (el) el.value = v; });
    if (q.get('date_from') || q.get('date_to')) range.value = 'custom';
  }

  async function load() {
    const p = params();
    history.replaceState(null, '', `?${p}`);
    document.getElementById('xlsx').href = `/stats/export.xlsx?${p}`;
    const root = document.getElementById('stats-root');
    root.style.opacity = last ? '0.55' : '1';                  // წინა გამოსახულება რჩება — ხტომის გარეშე
    try {
      const r = await fetch(`/api/stats?${p}`, { headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(r.status);
      last = await r.json();
      render(last);
    } catch (e) {
      document.getElementById('kpis').innerHTML = `<div class="notice err">სტატისტიკა ვერ ჩაიტვირთა (${esc(e.message)}).</div>`;
    } finally { root.style.opacity = '1'; }
  }

  // ── KPI ──────────────────────────────────────────────────────
  function tile(k, v, s, accent, href) {
    return `<div class="kpi ${accent || ''}"><div class="k">${k}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ''}${href ? `<a class="stretch" href="${href}" aria-label="${k}"></a>` : ''}</div>`;
  }
  function renderKpi(k) {
    const posRate = k.checked ? 100 * k.positive / k.checked : 0;
    const recRate = k.checked ? 100 * k.recommendation / k.checked : 0;
    document.getElementById('kpis').innerHTML = [
      tile('შემოწმებული', fmt(k.checked), `${fmt(k.sporadic)} სპორადული`, 'accent-info'),
      tile('დადებითი', fmt(k.positive), pct(Math.round(posRate * 10) / 10), 'accent-pos'),
      tile('ხარვეზი (უარყოფითი)', pct(k.defect_rate), `${fmt(k.negative)} ოქმი`, 'accent-neg'),
      tile('კრიტიკული ხარვეზი', pct(k.critical_rate), `${fmt(k.critical)} ოქმი ≥1 კრიტიკული კოდით`, 'accent-neg'),
      tile('რეკომენდაცია', fmt(k.recommendation), pct(Math.round(recRate * 10) / 10), 'accent-rec'),
      tile('უარყოფითიდან გასწორდა', pct(k.corrected_rate), `${fmt(k.corrected)} დადასტურებული (M)`, 'accent-pos'),
      tile('ველზე ღია', fmt(k.in_field), `${fmt(k.awaiting_qcm)} არ დათანხმებული QC მენეჯერთან`, 'accent-warn'),
      tile('დაზუსტების პროცესში', fmt(k.in_clarification), 'კითხვა გაგზავნილია — სტატუსი ჯერ არ აქვს', 'accent-cla'),
      tile('QC-ის გადასამოწმებელი', fmt(k.awaiting_qc), 'ველმა უპასუხა', 'accent-warn'),
      tile('გასავლელი', fmt(k.pending), 'ჯერ შეუმოწმებელი', ''),
      tile('პასუხის დრო (მედიანა)', k.response_median === null ? '—' : `${fmt(k.response_median)} დღე`,
        k.response_n ? `75%: ${fmt(k.response_p75)} დღე${k.response_legacy_share ? ` · ${k.response_legacy_share}% მიახლოებითი (ძველი ცხრილი)` : ''}` : '', ''),
    ].join('');
  }

  // ── ტენდენცია ────────────────────────────────────────────────
  function renderTrend(t) {
    const ch = chart('ch-trend');
    if (!ch) return;
    const x = t.map((d) => d.label);
    const mk = (name, key, color, top) => ({
      name, type: 'bar', stack: 'v', barMaxWidth: 26, data: t.map((d) => d[key]),
      itemStyle: { color, borderColor: C.surface, borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 },
      emphasis: { focus: 'series' },
    });
    ch.setOption(Object.assign(base(), {
      legend: { top: 0, left: 0, textStyle: { color: C.ink2, fontFamily: FONT }, itemWidth: 12, itemHeight: 10 },
      grid: { left: 8, right: 12, top: 34, bottom: 8, containLabel: true },
      tooltip: Object.assign(base().tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' } }),
      xAxis: Object.assign({ type: 'category', data: x }, axisCommon, { splitLine: { show: false } }),
      yAxis: Object.assign({ type: 'value' }, axisCommon),
      series: [mk('დადებითი', 'positive', C.pos), mk('რეკომენდაცია', 'recommendation', C.rec),
        mk('უარყოფითი', 'negative', C.neg, true)],
    }), true);

    const ch2 = chart('ch-rate');
    ch2.setOption(Object.assign(base(), {
      tooltip: Object.assign(base().tooltip, { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: C.axis } },
        valueFormatter: (v) => `${v}%` }),
      xAxis: Object.assign({ type: 'category', data: x, boundaryGap: false }, axisCommon, { splitLine: { show: false } }),
      yAxis: Object.assign({ type: 'value', axisLabel: { formatter: '{value}%', color: C.muted } }, axisCommon),
      series: [{ name: 'ხარვეზის %', type: 'line', data: t.map((d) => (d.reliable ? d.defect_rate : null)), smooth: false, connectNulls: false,
        lineStyle: { width: 2, color: C.series }, itemStyle: { color: C.series }, symbol: 'circle', symbolSize: 7,
        emphasis: { scale: 1.4 },
        markPoint: t.length ? { symbol: 'circle', symbolSize: 1, label: { show: true, position: 'top', color: C.ink2, formatter: (p) => `${p.value}%` },
          data: [{ type: 'max', name: 'მაქს.' }].concat(t[t.length - 1].reliable ? [{ coord: [x.length - 1, t[t.length - 1].defect_rate], value: t[t.length - 1].defect_rate }] : []) } : undefined }],
    }), true);
  }

  // ── ცხრილები (დალაგებადი) ─────────────────────────────────────
  function table(el, cols, rows, opts) {
    opts = opts || {};
    const host = document.getElementById(el);
    if (!host) return;
    let sortKey = opts.sort || cols[1].key, dir = -1;
    const draw = () => {
      const q = opts.search ? (document.getElementById(opts.search).value || '').toLowerCase() : '';
      const data = rows.filter((r) => !q || String(r.name || '').toLowerCase().includes(q))
        .sort((a, b) => ((a[sortKey] ?? -1) > (b[sortKey] ?? -1) ? 1 : -1) * dir);
      if (!data.length) { host.innerHTML = '<div class="empty">მონაცემი არ არის.</div>'; return; }
      host.innerHTML = `<table class="data compact"><thead><tr>${cols.map((c) =>
        `<th class="${c.num ? 'num' : ''}" data-k="${c.key}" style="cursor:pointer" title="დალაგება">${c.label}${c.key === sortKey ? (dir < 0 ? ' ↓' : ' ↑') : ''}</th>`).join('')}</tr></thead><tbody>${
        data.map((r) => `<tr>${cols.map((c) => `<td class="${c.num ? 'num' : ''}">${c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
      host.querySelectorAll('th').forEach((th) => th.addEventListener('click', () => {
        const k = th.dataset.k; if (k === sortKey) dir = -dir; else { sortKey = k; dir = -1; } draw();
      }));
    };
    if (opts.search) document.getElementById(opts.search).oninput = draw;
    draw();
  }
  const rateBar = (v) => `<span style="display:inline-flex;align-items:center;gap:6px;justify-content:flex-end;width:100%">${pct(v)}<span class="bar neg" style="width:60px"><span style="width:${Math.min(100, v || 0)}%"></span></span></span>`;
  const n = (v) => fmt(v);

  // ── კოდები ────────────────────────────────────────────────────
  function renderCodes(codes) {
    const top = codes.filter((c) => c.negative > 0).slice(0, 15).reverse();
    const ch = chart('ch-codes');
    if (ch) ch.setOption(Object.assign(base(), {
      grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
      tooltip: Object.assign(base().tooltip, { trigger: 'item',
        formatter: (p) => { const c = top[p.dataIndex]; return `<b>${esc(c.code)}</b> — ${esc(c.name || '')}<br>${esc(c.group || '')} · ${c.severity === 'Critical' ? 'კრიტიკული' : 'მნიშვნელოვანი'}<br>უარყოფით ოქმებში: <b>${fmt(c.negative)}</b>`; } }),
      xAxis: Object.assign({ type: 'value' }, axisCommon),
      yAxis: Object.assign({ type: 'category', data: top.map((c) => c.code) }, axisCommon, { splitLine: { show: false } }),
      series: [{ type: 'bar', barMaxWidth: 16, data: top.map((c) => ({ value: c.negative,
        itemStyle: { color: c.severity === 'Critical' ? C.neg : C.rec, borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: 'right', color: C.ink2, fontSize: 11, formatter: (p) => fmt(p.value) } }],
    }), true);
    table('t-codes', [
      { key: 'code', label: 'კოდი', fmt: (v, r) => `<span class="code sev-${r.severity}">${esc(v)}</span>` },
      { key: 'name', label: 'დასახელება' },
      { key: 'negative', label: 'უარყოფითში', num: true, fmt: n },
      { key: 'recommendation', label: 'რეკომენდაციაში', num: true, fmt: n },
    ], codes, { sort: 'negative' });
  }

  // ── ზონები (რუკა) ─────────────────────────────────────────────
  async function renderZones(z) {
    table('t-zones', [
      { key: 'zone', label: 'ზონა' }, { key: 'name', label: 'დასახელება' },
      { key: 'checked', label: 'შემოწმებული', num: true, fmt: n },
      { key: 'negative', label: 'უარყოფითი', num: true, fmt: n },
      { key: 'defect_rate', label: 'ხარვეზი %', num: true, fmt: rateBar },
    ], z, { sort: 'checked' });
    const ch = chart('ch-map');
    if (!ch) return;
    if (!zonesGeo) {
      zonesGeo = await (await fetch('/static/geo/zones.geojson')).json();
      echarts.registerMap('zones', zonesGeo);
    }
    const data = z.map((d) => ({ name: d.zone, value: d.defect_rate, checked: d.checked, label: d.name }));
    const max = Math.max(10, ...z.map((d) => d.defect_rate || 0));
    ch.setOption(Object.assign(base(), {
      tooltip: Object.assign(base().tooltip, { trigger: 'item', formatter: (p) => {
        const d = p.data;
        if (!d) return `${esc(p.name)} — მონაცემი არ არის`;
        return `<b>${esc(d.name)} ${esc(d.label || '')}</b><br>შემოწმებული: ${fmt(d.checked)}<br>ხარვეზი: <b>${pct(d.value)}</b>`;
      } }),
      visualMap: { min: 0, max: Math.ceil(max), left: 8, bottom: 8, orient: 'horizontal', calculable: true,
        text: [`${Math.ceil(max)}%`, '0%'], textStyle: { color: C.muted, fontFamily: FONT },
        inRange: { color: C.ramp }, itemWidth: 10, itemHeight: 120 },
      series: [{ type: 'map', map: 'zones', nameProperty: 'id', roam: true, data,
        itemStyle: { areaColor: '#f1f3f5', borderColor: '#ffffff', borderWidth: 0.8 },
        emphasis: { label: { show: false }, itemStyle: { areaColor: '#f3d14c' } },
        select: { disabled: true }, label: { show: false } }],
    }), true);
  }

  function render(d) {
    const sec = new Set(d.sections);
    document.querySelectorAll('[data-sec]').forEach((el) => { el.hidden = !sec.has(el.dataset.sec); });
    if (d.kpi) renderKpi(d.kpi);
    if (d.trend) renderTrend(d.trend);
    if (d.operators) table('t-operators', [
      { key: 'name', label: 'ოპერატორი' },
      { key: 'passed', label: 'გავლილი', num: true, fmt: n },
      { key: 'checked', label: 'შემოწმებული (სტატუსით)', num: true, fmt: n },
      { key: 'positive', label: 'დადებითი', num: true, fmt: n },
      { key: 'negative', label: 'უარყოფითი', num: true, fmt: n },
      { key: 'recommendation', label: 'რეკომ.', num: true, fmt: n },
      { key: 'defect_rate', label: 'ხარვეზი %', num: true, fmt: rateBar },
      { key: 'pending', label: 'გასავლელი', num: true, fmt: n },
      { key: 'awaiting_qc', label: 'დაბრუნებული შესამოწმებელი', num: true, fmt: n },
      { key: 'returned', label: 'QC-მ დააბრუნა', num: true, fmt: n },
      { key: 'daily_avg', label: 'დღიური საშ.', num: true, fmt: n },
      { key: 'sporadic', label: 'მ.შ. სპორადული', num: true, fmt: n },
    ], d.operators, { sort: 'checked' });
    if (d.managers) table('t-managers', [
      { key: 'name', label: 'მენეჯერი' },
      { key: 'checked', label: 'შემოწმებული', num: true, fmt: n },
      { key: 'negative', label: 'უარყოფითი', num: true, fmt: n },
      { key: 'defect_rate', label: 'ხარვეზი %', num: true, fmt: rateBar },
      { key: 'critical_rate', label: 'კრიტიკული %', num: true, fmt: pct },
      { key: 'corrected_rate', label: 'გასწორდა %', num: true, fmt: pct },
      { key: 'in_field', label: 'ველზე ღია', num: true, fmt: n },
      { key: 'disputed', label: 'არ დათანხმება', num: true, fmt: n },
      { key: 'median_response_days', label: 'პასუხის დრო', num: true, fmt: (v) => v === null || v === undefined ? '—' : `${fmt(v)} დღე` },
    ], d.managers, { sort: 'checked' });
    if (d.surveyors) table('t-surveyors', [
      { key: 'name', label: 'ამზომველი' },
      { key: 'checked', label: 'შემოწმებული', num: true, fmt: n },
      { key: 'positive', label: 'დადებითი', num: true, fmt: n },
      { key: 'negative', label: 'უარყოფითი', num: true, fmt: n },
      { key: 'recommendation', label: 'რეკომ.', num: true, fmt: n },
      { key: 'defect_rate', label: 'ხარვეზი %', num: true, fmt: rateBar },
      { key: 'corrected', label: 'გასწორდა', num: true, fmt: n },
      { key: 'in_field', label: 'დარჩა გასასწორებელი', num: true, fmt: n },
      { key: 'disputed', label: 'არ დაეთანხმა', num: true, fmt: n },
    ], d.surveyors, { sort: 'checked', search: 'surv-q' });
    if (d.codes) renderCodes(d.codes);
    if (d.zones) renderZones(d.zones);
    if (d.restricted) {
      const r = d.restricted;
      if (r.qc_errors) table('t-qcerr', [
        { key: 'name', label: 'ოპერატორი' },
        { key: 'errors_total', label: 'შეცდომა სულ', num: true, fmt: n },
        { key: 'qc_errors', label: 'ველი მართალია', num: true, fmt: n },
        { key: 'wrong_defect', label: 'არასწორი ხარვეზი', num: true, fmt: n },
        { key: 'missed_defect', label: 'გამორჩენილი', num: true, fmt: n },
        { key: 'incomplete_info', label: 'არასრულყოფილი ინფ.', num: true, fmt: n },
        { key: 'correct', label: 'სწორია', num: true, fmt: n },
        { key: 'reviewed', label: 'შეფასებული', num: true, fmt: n },
        { key: 'both_right', label: 'ორივე მართალია', num: true, fmt: n },
        { key: 'checked', label: 'შემოწმებული', num: true, fmt: n },
      ], r.qc_errors, { sort: 'errors_total' });
      const lf = document.getElementById('legacy-flags');
      if (lf && r.review_sources) {
        const s = r.review_sources;
        lf.textContent = `შეფასებებიდან ${fmt(s.legacy)} — ძველი ცხრილის TYPE სვეტიდან, ${fmt(s.manual)} — ახალ სისტემაში.`;
      }
      if (r.false_fix_by_manager) table('t-falsefix', [
        { key: 'name', label: 'საველე მენეჯერი' },
        { key: 'false_fix', label: 'ცრუ „შესწორდა“', num: true, fmt: n },
        { key: 'returned_items', label: 'დაბრუნებული შემთხვევა', num: true, fmt: n },
        { key: 'returns', label: 'დაბრუნება სულ', num: true, fmt: n },
      ], r.false_fix_by_manager, { sort: 'returns' });
    }
  }

  restore();
  load();
})();
