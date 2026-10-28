/* სტატისტიკა — ფილტრები ერთ რიგში, ყველა დიაგრამა ერთსა და იმავე ჭრილზე.
   ვიზუალი: qc-dashboard-main-ის მიდგომა (დანომრილი სექციები, ფერადი KPI, საშუალოს ხაზი,
   კოდების რეიტინგი, ყვითლიდან წითლამდე რუკა რეიტინგით, დასკვნები) „იზოხაზის“ ტოკენებით.
   ფერები: დადებითი #0a8f5f · რეკომენდაცია #e08600 · უარყოფითი #d92d20 — ყოველ დიაგრამას
   ცხრილი ახლავს (ფერი მარტო მნიშვნელობას არ ატარებს). მონაცემი — მხოლოდ /api/stats. */
(function () {
  'use strict';
  const C = {
    pos: '#0a8f5f', rec: '#e08600', neg: '#d92d20', series: '#2a55d9', crit: '#d92d20',
    ink: '#14181f', ink2: '#4b505c', muted: '#6f737d', grid: '#e4e0d5', axis: '#d3cec1',
    surface: '#fcfbf8', empty: '#efece4',
    ramp: ['#fffbe0', '#ffe7a0', '#fbc75a', '#f4913a', '#dc3f1c', '#8f1a10'],
  };
  const MIN_ZONE = 10;               // ზონა <10 შემოწმებით ფერს არ იღებს (qc-dashboard-main-ის წესი)
  // ჩარჩოს და მონაცემის ფერები app.css-ის ტოკენებიდან — ღია და მუქი თემისთვის
  function themeColors() {
    const s = getComputedStyle(document.documentElement);
    const v = (name, fb) => (s.getPropertyValue(name) || '').trim() || fb;
    const dark = document.documentElement.dataset.theme === 'dark';
    Object.assign(C, {
      ink: v('--text', C.ink), ink2: v('--text-2', C.ink2), muted: v('--muted', C.muted),
      grid: v('--hairline', C.grid), axis: v('--border-strong', C.axis), surface: v('--card', C.surface),
      empty: v('--sunk', C.empty), series: v('--accent', C.series),
      pos: v('--pos', C.pos), rec: v('--major', C.rec), neg: v('--neg', C.neg), crit: v('--crit', C.crit),
      ramp: dark ? ['#3a3417', '#6b5419', '#a3701c', '#c95a22', '#e0442a', '#ff8a7a'] : ['#fffbe0', '#ffe7a0', '#fbc75a', '#f4913a', '#dc3f1c', '#8f1a10'],
    });
  }
  themeColors();
  document.addEventListener('qcp:theme', () => { themeColors(); if (last) render(last); });

  const FONT = '"Noto Sans Georgian", "Segoe UI", system-ui, sans-serif';
  const fmt = (n) => (n === null || n === undefined) ? '—' :
    (Number.isInteger(n) ? n.toLocaleString('en-US').replace(/,/g, ' ') : (Math.round(n * 10) / 10).toString());
  const pct = (n) => (n === null || n === undefined) ? '—' : `${fmt(n)}%`;
  const p1 = (n) => Math.round(n * 10) / 10;
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const charts = {};
  let zonesGeo = null;
  let last = null;
  let trendMode = 'pct';

  function chart(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (!charts[id] || charts[id].getDom() !== el) charts[id] = echarts.init(el, null, { renderer: 'canvas' });
    return charts[id];
  }
  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c && c.resize()));

  const tip = () => ({
    backgroundColor: C.surface, borderColor: C.axis, borderWidth: 1, padding: [9, 12],
    textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12.5 },
    extraCssText: 'box-shadow:0 10px 28px rgba(16,24,40,.16);border-radius:10px;',
  });
  const base = () => ({
    aria: { enabled: true },
    textStyle: { fontFamily: FONT, color: C.ink, fontSize: 12 },
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: tip(),
    animationDuration: 700, animationEasing: 'cubicOut',
  });
  const axisCat = () => ({ axisLine: { lineStyle: { color: C.axis } }, axisTick: { show: false }, axisLabel: { color: C.ink2, fontFamily: FONT, fontSize: 11.5 }, splitLine: { show: false } });
  const axisVal = (unit) => ({ axisLine: { show: false }, axisTick: { show: false }, name: unit || '', nameTextStyle: { color: C.muted, fontSize: 11 },
    axisLabel: { color: C.muted, fontFamily: FONT, fontSize: 11, formatter: unit === '%' ? '{value}%' : '{value}' },
    splitLine: { lineStyle: { color: C.grid, type: 'dashed' } } });
  // სიმძიმე: კოდი შეიძლება ცნობარში არ იყოს (outer join) — მაშინ „—“ და არა „მნიშვნელოვანი“
  const SEV = { Critical: 'კრიტიკული', Major: 'მნიშვნელოვანი' };
  const sevLabel = (s) => SEV[s] || '—';
  const sevColor = (s) => (s === 'Critical' ? C.crit : s === 'Major' ? C.rec : C.muted);
  const dot = (c) => `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${c};margin-right:6px"></span>`;

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

  const modeSeg = document.getElementById('trend-mode');
  if (modeSeg) modeSeg.addEventListener('click', (e) => {
    const b = e.target.closest('[data-mode]');
    if (!b) return;
    trendMode = b.dataset.mode;
    modeSeg.querySelectorAll('[data-mode]').forEach((x) => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
    if (last && last.trend) renderTrend(last.trend);
  });

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
  function scope() {
    const el = document.getElementById('stats-scope');
    if (!el) return;
    const parts = [];
    form.querySelectorAll('select, input').forEach((f) => {
      if (!f.value || f.type === 'hidden' || f.id === 's-range' && f.value === 'all') return;
      const lbl = form.querySelector(`label[for="${f.id}"]`);
      const val = f.tagName === 'SELECT' ? f.selectedOptions[0].textContent : f.value;
      parts.push(`${esc(lbl ? lbl.textContent.replace(/\s*\(.*\)/, '') : f.name)}: <b>${esc(val)}</b>`);
    });
    el.innerHTML = parts.length ? parts.join(' · ') : 'ჭრილი: <b>მთელი სისტემა, მთელი პერიოდი</b>';
  }

  async function load() {
    const p = params();
    history.replaceState(null, '', `?${p}`);
    document.getElementById('xlsx').href = `/stats/export.xlsx?${p}`;
    scope();
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

  // ── KPI: სამი ჯგუფი — მოცულობა / ხარისხი / პროცესი ───────────────
  function tile(k, v, s, accent, extra) {
    return `<div class="kpi ${accent || ''} ${extra || ''}"><div class="k">${k}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ''}</div>`;
  }
  function renderKpi(k) {
    const posRate = k.checked ? 100 * k.positive / k.checked : 0;
    const recRate = k.checked ? 100 * k.recommendation / k.checked : 0;
    const group = (title, tiles) => `<section class="kpi-group"><h3>${title}</h3><div class="kpis">${tiles.join('')}</div></section>`;
    document.getElementById('kpis').innerHTML = '<div class="kpi-groups">' + [
      group('მოცულობა', [
        tile('შემოწმებული ოქმები', fmt(k.checked), `${fmt(k.sporadic)} სპორადული · ${fmt(k.pending)} ჯერ გასავლელი`, 'accent-info', 'hero'),
        tile('დადებითი', fmt(k.positive), `${pct(p1(posRate))} შემოწმებულიდან`, 'accent-pos'),
        tile('რეკომენდაცია', fmt(k.recommendation), `${pct(p1(recRate))} შემოწმებულიდან`, 'accent-rec'),
      ]),
      group('ხარისხი', [
        tile('ხარვეზი (უარყოფითი)', pct(k.defect_rate), `${fmt(k.negative)} ოქმი`, 'accent-neg', 'hero'),
        tile('კრიტიკული ხარვეზი', pct(k.critical_rate), `${fmt(k.critical)} ოქმი ≥1 კრიტიკულით`, 'accent-neg'),
        tile('უარყოფითიდან გასწორდა', pct(k.corrected_rate), `${fmt(k.corrected)} დადასტურებული (M)`, 'accent-pos'),
      ]),
      group('პროცესი', [
        // ვისთან არის დავა — სერვერი როლით წყვეტს: ველს „ხარისხის კონტროლთან“ (T-031)
        tile('ველზე ღია', fmt(k.in_field), `${fmt(k.awaiting_qcm)} არ დათანხმებული ${esc(document.getElementById('kpis').dataset.qcmWhere || 'QC მენეჯერთან')}`, 'accent-warn'),
        tile('QC-ის გადასამოწმებელი', fmt(k.awaiting_qc), 'ველმა უპასუხა', 'accent-warn'),
        tile('დაზუსტების პროცესში', fmt(k.in_clarification), 'კითხვა გაგზავნილია', 'accent-cla'),
        tile('პასუხის დრო (მედიანა)', k.response_median === null ? '—' : `${fmt(k.response_median)} დღე`,
          k.response_n ? `75%: ${fmt(k.response_p75)} დღე${k.response_legacy_share ? ` · ${k.response_legacy_share}% მიახლოებითი` : ''}` : '', 'accent-info'),
      ]),
    ].join('') + '</div>';
  }

  // ── დიაგრამა 1: შედეგები კვირების მიხედვით (პროცენტი ↔ რაოდენობა) ──
  function renderTrend(t) {
    const ch = chart('ch-trend');
    if (!ch) return;
    const x = t.map((d) => d.label);
    const asPct = trendMode === 'pct';
    // მნიშვნელი — Backend-ის „checked“ (იგივე, რაც defect_rate-ში); ძველი პასუხისთვის — ჯამი
    const tot = t.map((d) => d.checked || ((d.positive || 0) + (d.recommendation || 0) + (d.negative || 0)));
    const defs = [['დადებითი', 'positive', C.pos], ['რეკომენდაცია', 'recommendation', C.rec], ['უარყოფითი', 'negative', C.neg]];
    ch.setOption(Object.assign(base(), {
      legend: { top: 0, left: 0, textStyle: { color: C.ink2, fontFamily: FONT }, itemWidth: 14, itemHeight: 9, itemGap: 16 },
      grid: { left: 8, right: 12, top: 38, bottom: 8, containLabel: true },
      tooltip: Object.assign(tip(), { trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(42,85,217,.06)' } },
        formatter: (ps) => {
          const i = ps[0].dataIndex;
          return `<b>${esc(x[i])}</b><br><span style="color:${C.muted}">სულ: ${fmt(tot[i])}</span><br>` +
            defs.map((d) => `${dot(d[2])}${d[0]}: <b>${fmt(t[i][d[1]])}</b> (${pct(tot[i] ? p1(100 * t[i][d[1]] / tot[i]) : 0)})`).join('<br>');
        } }),
      xAxis: Object.assign({ type: 'category', data: x }, axisCat()),
      yAxis: Object.assign({ type: 'value', max: asPct ? 100 : null }, axisVal(asPct ? '%' : 'ოქმი')),
      series: defs.map((d, k) => ({
        name: d[0], type: 'bar', stack: 'v', barMaxWidth: 30,
        data: t.map((r, i) => asPct ? (tot[i] && (r.reliable !== false) ? p1(100 * r[d[1]] / tot[i]) : null) : r[d[1]]),
        itemStyle: { color: d[2], borderColor: C.surface, borderWidth: 1, borderRadius: k === 2 ? [5, 5, 0, 0] : 0 },
        emphasis: { focus: 'series' },
        label: { show: asPct && k === 2, position: 'insideTop', color: '#fff', fontSize: 10, fontWeight: 600, formatter: (p) => p.value ? `${p.value}%` : '' },
      })),
    }), true);

    const ch2 = chart('ch-rate');
    if (!ch2) return;
    const rel = t.filter((d) => d.reliable && d.defect_rate !== null);
    const avg = rel.length ? p1(rel.reduce((a, d) => a + d.negative, 0) * 100 / Math.max(1, rel.reduce((a, d) => a + (d.checked || (d.positive + d.recommendation + d.negative)), 0))) : null;
    ch2.setOption(Object.assign(base(), {
      grid: { left: 8, right: 18, top: 26, bottom: 8, containLabel: true },
      tooltip: Object.assign(tip(), { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: C.axis } }, valueFormatter: (v) => (v === null ? '—' : `${v}%`) }),
      xAxis: Object.assign({ type: 'category', data: x, boundaryGap: false }, axisCat()),
      yAxis: Object.assign({ type: 'value' }, axisVal('%')),
      series: [{ name: 'ხარვეზის %', type: 'line', data: t.map((d) => (d.reliable ? d.defect_rate : null)), smooth: .25, connectNulls: false,
        lineStyle: { width: 2.6, color: C.series }, itemStyle: { color: C.series, borderColor: C.surface, borderWidth: 2 }, symbol: 'circle', symbolSize: 8,
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(42,85,217,.20)' }, { offset: 1, color: 'rgba(42,85,217,0)' }]) },
        label: { show: true, position: 'top', color: C.ink2, fontSize: 10.5, fontWeight: 600, formatter: (p) => (p.value === null ? '' : `${p.value}%`) },
        markLine: avg === null ? undefined : { silent: true, symbol: 'none', data: [{ yAxis: avg }], lineStyle: { color: C.muted, type: 'dashed', width: 1 },
          label: { formatter: `საშუალო ${avg}%`, color: C.muted, fontSize: 10.5, position: 'insideEndTop' } } }],
    }), true);
  }

  // ── დიაგრამა 2: ხარვეზის % მენეჯერების მიხედვით + საშუალოს ხაზი ──────
  function renderManagerChart(rows, baseline) {
    const ch = chart('ch-managers');
    if (!ch) return;
    const data = rows.filter((r) => r.checked).slice().sort((a, b) => (b.defect_rate || 0) - (a.defect_rate || 0));
    const el = document.getElementById('ch-managers');
    el.style.height = Math.max(240, data.length * 34 + 60) + 'px';
    ch.resize();
    // საშუალო — ამავე ჭრილის საერთო ხარვეზის % (kpi.defect_rate). მენეჯერების ჯამი არ გამოდგება:
    // ოქმი ყველა მიკუთვნებულ მენეჯერს ეთვლება (by_manager) და ზოგი ოქმი ორჯერ მოხვდებოდა.
    const tc = data.reduce((a, r) => a + r.checked, 0), tn = data.reduce((a, r) => a + (r.negative || 0), 0);
    const avg = (baseline !== null && baseline !== undefined) ? p1(baseline) : (tc ? p1(100 * tn / tc) : 0);
    ch.setOption(Object.assign(base(), {
      grid: { left: 8, right: 56, top: 22, bottom: 8, containLabel: true },
      tooltip: Object.assign(tip(), { trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(42,85,217,.06)' } },
        formatter: (ps) => { const d = data[ps[0].dataIndex]; return `<b>${esc(d.name)}</b><br>შემოწმებული: <b>${fmt(d.checked)}</b><br>უარყოფითი: <b>${fmt(d.negative)}</b> (${pct(d.defect_rate)})<br>კრიტიკული: ${pct(d.critical_rate)} · გასწორდა: ${pct(d.corrected_rate)}<br><span style="color:${C.muted}">საშუალო: ${avg}%</span>`; } }),
      xAxis: Object.assign({ type: 'value' }, axisVal('%')),
      yAxis: Object.assign({ type: 'category', data: data.map((d) => d.name), inverse: true }, axisCat()),
      series: [{ type: 'bar', barMaxWidth: 18,
        data: data.map((d) => ({ value: d.defect_rate, itemStyle: { color: d.defect_rate > avg ? C.neg : C.series, borderRadius: [0, 5, 5, 0], opacity: d.defect_rate > avg ? 1 : .75 } })),
        label: { show: true, position: 'right', color: C.ink2, fontSize: 11, fontWeight: 600, formatter: '{c}%' },
        markLine: { silent: true, symbol: 'none', data: [{ xAxis: avg }], lineStyle: { color: C.muted, type: 'dashed', width: 1 },
          label: { formatter: `საშუალო ${avg}%`, color: C.muted, fontSize: 10.5, position: 'end' } } }],
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
  const rateBar = (v) => `<span style="display:inline-flex;align-items:center;gap:8px;justify-content:flex-end;width:100%">${pct(v)}<span class="bar neg" style="width:64px"><span style="width:${Math.min(100, v || 0)}%"></span></span></span>`;
  const n = (v) => fmt(v);

  // ── დიაგრამა 4: კოდები — წილი + რეიტინგი ──────────────────────────
  function renderCodes(codes) {
    const neg = codes.filter((c) => c.negative > 0);
    const total = neg.reduce((a, c) => a + c.negative, 0) || 1;
    const top = neg.slice(0, 15);
    const ch = chart('ch-codes');
    if (ch) {
      const el = document.getElementById('ch-codes');
      el.style.height = Math.max(320, top.length * 28 + 40) + 'px';
      ch.resize();
      ch.setOption(Object.assign(base(), {
        grid: { left: 8, right: 52, top: 8, bottom: 8, containLabel: true },
        tooltip: Object.assign(tip(), { trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(42,85,217,.06)' } },
          formatter: (ps) => { const c = top[ps[0].dataIndex]; return `<b>${esc(c.code)}</b> — ${esc(c.name || '')}<br><span style="color:${C.muted}">${esc(c.group || '')} · ${sevLabel(c.severity)}</span><br>უარყოფით ოქმებში: <b>${fmt(c.negative)}</b> · წილი <b>${p1(100 * c.negative / total)}%</b>`; } }),
        xAxis: Object.assign({ type: 'value' }, axisVal('%')),
        yAxis: Object.assign({ type: 'category', inverse: true, data: top.map((c, i) => `{n|${i + 1}} {cd|${c.code}}`) }, axisCat(),
          { axisLabel: { color: C.ink2, fontFamily: FONT, rich: { n: { color: C.ink, fontWeight: 800, fontSize: 11.5, padding: [0, 4, 0, 0] }, cd: { color: C.ink2, fontWeight: 600, fontSize: 11.5, fontFamily: 'JetBrains Mono, Consolas, monospace' } } } }),
        series: [{ type: 'bar', barMaxWidth: 16, data: top.map((c) => ({ value: p1(100 * c.negative / total),
          itemStyle: { color: sevColor(c.severity), borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: 'right', color: C.ink2, fontSize: 10.5, fontWeight: 600, formatter: '{c}%' } }],
      }), true);
    }
    const host = document.getElementById('t-codes');
    if (host) {
      host.innerHTML = neg.length ? `<table class="data compact"><thead><tr><th style="width:44px">რიგი</th><th>ხარვეზის კოდი და დასახელება</th><th class="num">უარყ.</th><th class="num">რეკომ.</th><th class="num">წილი</th></tr></thead><tbody>${
        codes.map((c, i) => `<tr><td><span class="rank">${i + 1}</span></td><td><span class="code sev-${esc(c.severity)}">${esc(c.code)}</span> ${SEV[c.severity] ? `<span class="sev ${esc(c.severity)}">${sevLabel(c.severity)}</span>` : ''}<span class="tname">${esc(c.name || '')}</span></td><td class="num">${fmt(c.negative)}</td><td class="num">${fmt(c.recommendation)}</td><td class="num"><b>${c.negative ? p1(100 * c.negative / total) + '%' : '—'}</b></td></tr>`).join('')}</tbody></table>` : '<div class="empty">ხარვეზის კოდი არ არის.</div>';
    }
  }

  // ── დიაგრამა 5: ზონები — რუკა (GIS) + რეიტინგი ─────────────────────
  async function renderZones(z) {
    table('t-zones', [
      { key: 'zone', label: 'ზონა' }, { key: 'name', label: 'დასახელება' },
      { key: 'checked', label: 'შემოწმებული', num: true, fmt: n },
      { key: 'negative', label: 'უარყოფითი', num: true, fmt: n },
      { key: 'defect_rate', label: 'ხარვეზი %', num: true, fmt: rateBar },
    ], z, { sort: 'checked' });
    const reliable = z.filter((d) => d.checked >= MIN_ZONE && d.defect_rate !== null).sort((a, b) => b.defect_rate - a.defect_rate);
    const panel = document.getElementById('zone-rank');
    if (panel) {
      const tc = z.reduce((a, d) => a + d.checked, 0), tn = z.reduce((a, d) => a + d.negative, 0);
      panel.innerHTML = `<h4>ზონების რეიტინგი</h4><div class="sub">ხარვეზის % · მხოლოდ ≥${MIN_ZONE} შემოწმებით · საშუალო <b>${tc ? p1(100 * tn / tc) : 0}%</b></div>` +
        reliable.slice(0, 14).map((d, i) => `<button type="button" class="rank-row" data-zone="${esc(d.zone)}"><span class="pos">${i + 1}</span><span class="zn">${esc(d.zone)} · ${esc(d.name || '')}</span><span class="rt" style="color:${d.defect_rate > (tc ? 100 * tn / tc : 0) ? C.neg : C.ink}">${p1(d.defect_rate)}%</span><span class="qt">${fmt(d.checked)}</span></button>`).join('') +
        (reliable.length ? '' : '<div class="empty">საკმარისი მონაცემი არ არის.</div>');
    }
    const ch = chart('ch-map');
    if (!ch) return;
    if (!zonesGeo) {
      zonesGeo = await (await fetch('/static/geo/zones.geojson')).json();
      echarts.registerMap('zones', zonesGeo);
    }
    const data = z.map((d) => ({ name: d.zone, value: d.checked >= MIN_ZONE ? d.defect_rate : null, checked: d.checked, label: d.name, rate: d.defect_rate }));
    const max = Math.max(10, ...reliable.map((d) => d.defect_rate || 0));
    ch.setOption(Object.assign(base(), {
      tooltip: Object.assign(tip(), { trigger: 'item', formatter: (p) => {
        const d = p.data;
        if (!d) return `${esc(p.name)} — მონაცემი არ არის`;
        return `<b>${esc(d.name)} · ${esc(d.label || '')}</b><br>შემოწმებული: ${fmt(d.checked)}<br>ხარვეზი: <b>${pct(d.rate)}</b>${d.value === null ? `<br><span style="color:${C.muted}">&lt;${MIN_ZONE} შემოწმება — ფერი არ ენიჭება</span>` : ''}`;
      } }),
      visualMap: { min: 0, max: Math.ceil(max), left: 8, bottom: 8, orient: 'horizontal', calculable: true,
        text: [`${Math.ceil(max)}%`, '0%'], textStyle: { color: C.muted, fontFamily: FONT }, inRange: { color: C.ramp }, itemWidth: 10, itemHeight: 140 },
      series: [{ type: 'map', map: 'zones', nameProperty: 'id', roam: true, data, scaleLimit: { min: 1, max: 8 },
        itemStyle: { areaColor: C.empty, borderColor: C.surface, borderWidth: 0.8 },
        emphasis: { label: { show: false }, itemStyle: { areaColor: '#8fbdf5', borderColor: C.ink, borderWidth: 1 } },
        select: { disabled: true }, label: { show: false } }],
    }), true);
    if (panel && !panel.dataset.bound) {
      panel.dataset.bound = '1';
      panel.addEventListener('click', (e) => {
        const b = e.target.closest('[data-zone]');
        if (!b) return;
        ch.dispatchAction({ type: 'downplay' });
        ch.dispatchAction({ type: 'highlight', name: b.dataset.zone });
        ch.dispatchAction({ type: 'showTip', name: b.dataset.zone, seriesIndex: 0 });
      });
    }
  }

  // ── შეჯამება და დასკვნები — მხოლოდ ამავე პასუხიდან გამოთვლილი ─────────
  function renderInsights(d) {
    const host = document.getElementById('insights');
    if (!host) return;
    const k = d.kpi || {}, out = [];
    if (k.checked) out.push({ t: 'საერთო მაჩვენებელი', cls: '', v: `შემოწმებულია <b>${fmt(k.checked)}</b> ოქმი. ხარვეზიანია <b>${fmt(k.negative)}</b> (<b>${pct(k.defect_rate)}</b>), რეკომენდაციით — <b>${fmt(k.recommendation)}</b>.` });
    if (k.checked) out.push({ t: 'კრიტიკული ხარვეზი', cls: 'crit', v: `კრიტიკული კოდი აქვს <b>${fmt(k.critical)}</b> ოქმს — შემოწმებულის <b>${pct(k.critical_rate)}</b>. უარყოფითიდან გასწორდა <b>${pct(k.corrected_rate)}</b>.` });
    const codes = (d.codes || []).filter((c) => c.negative > 0);
    if (codes.length) {
      const tot = codes.reduce((a, c) => a + c.negative, 0);
      out.push({ t: 'ყველაზე ხშირი ხარვეზი', cls: '', v: `<b>${esc(codes[0].code)}</b> — ${esc(codes[0].name || '')}. <b>${fmt(codes[0].negative)}</b> უარყოფით ოქმში (${p1(100 * codes[0].negative / tot)}%).` });
      const crit = codes.find((c) => c.severity === 'Critical');
      if (crit && crit !== codes[0]) out.push({ t: 'ყველაზე ხშირი კრიტიკული', cls: 'crit', v: `<b>${esc(crit.code)}</b> — ${esc(crit.name || '')}. <b>${fmt(crit.negative)}</b> ოქმში.` });
    }
    const zones = (d.zones || []).filter((z) => z.checked >= MIN_ZONE).sort((a, b) => b.defect_rate - a.defect_rate);
    if (zones.length > 1) out.push({ t: 'ზონები', cls: 'warn', v: `ყველაზე მაღალი ხარვეზის % — <b>${esc(zones[0].zone)} ${esc(zones[0].name || '')}</b> (${pct(zones[0].defect_rate)}), ყველაზე დაბალი — <b>${esc(zones[zones.length - 1].zone)} ${esc(zones[zones.length - 1].name || '')}</b> (${pct(zones[zones.length - 1].defect_rate)}).` });
    if (k.response_median !== null && k.response_median !== undefined) out.push({ t: 'ველის პასუხის დრო', cls: 'good', v: `პასუხი საშუალოდ (მედიანა) <b>${fmt(k.response_median)} დღეში</b> მოდის; 75% — ${fmt(k.response_p75)} დღეში.` });
    host.innerHTML = out.map((o) => `<div class="ins ${o.cls}"><div class="t">${o.t}</div><div class="v">${o.v}</div></div>`).join('') ||
      '<div class="ins"><div class="v">არჩეულ ჭრილში მონაცემი არ არის.</div></div>';
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
    if (d.managers) {
      renderManagerChart(d.managers, d.kpi ? d.kpi.defect_rate : null);
      table('t-managers', [
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
    }
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
    renderInsights(d);
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
