/* საცდელი: სტატისტიკა Tabler-ის დიზაინით. მონაცემი — იგივე /api/stats, რასაც ძველი გვერდი იყენებს. */
(function () {
  'use strict';
  const C = { pos: '#1baf7a', rec: '#eda100', neg: '#d03b3b', ink: '#1d2530', muted: '#66727f', grid: '#e7ebf0', axis: '#c3cbd6' };
  const FONT = '"Noto Sans Georgian", "Segoe UI", system-ui, sans-serif';
  const fmt = (n) => (n === null || n === undefined) ? '—' :
    (Number.isInteger(n) ? n.toLocaleString('en-US').replace(/,/g, ' ') : (Math.round(n * 10) / 10).toString());
  const pct = (n) => (n === null || n === undefined) ? '—' : `${fmt(n)}%`;
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const $ = (id) => document.getElementById(id);
  let chart = null;
  window.addEventListener('resize', () => chart && chart.resize());

  function params() {
    const p = new URLSearchParams();
    const r = $('p-range').value;
    if (r !== 'all') {
      const to = new Date(), from = new Date(Date.now() - Number(r) * 86400000);
      const iso = (d) => d.toISOString().slice(0, 10);
      p.set('date_from', iso(from)); p.set('date_to', iso(to));
    }
    if ($('p-kind').value) p.set('kind', $('p-kind').value);
    return p;
  }

  function card(label, value, sub, color) {
    return `<div class="col-sm-6 col-lg-3"><div class="card"><div class="card-body">
      <div class="subheader">${label}</div>
      <div class="kpi-v mt-1 ${color || ''}">${value}</div>
      ${sub ? `<div class="text-muted small mt-1">${sub}</div>` : ''}
    </div></div></div>`;
  }

  function renderKpi(k) {
    const posRate = k.checked ? 100 * k.positive / k.checked : 0;
    $('kpis').innerHTML = [
      card('შემოწმებული', fmt(k.checked), `${fmt(k.sporadic)} სპორადული`),
      card('დადებითი', fmt(k.positive), pct(Math.round(posRate * 10) / 10), 'text-green'),
      card('ხარვეზი (უარყოფითი)', pct(k.defect_rate), `${fmt(k.negative)} ოქმი`, 'text-red'),
      card('კრიტიკული ხარვეზი', pct(k.critical_rate), `${fmt(k.critical)} ოქმი ≥1 კრიტიკული კოდით`, 'text-red'),
      card('უარყოფითიდან გასწორდა', pct(k.corrected_rate), `${fmt(k.corrected)} დადასტურებული`, 'text-green'),
      // სტატუსის წარწერა — D.labels(role)-იდან (#kpis data-qcm-state): ველს „… ხარისხის კონტროლთან“ (T-031)
    card('ველზე ღია', fmt(k.in_field), `${fmt(k.awaiting_qcm)} ${esc($('kpis').dataset.qcmState)}`, 'text-orange'),
      card('QC-ის გადასამოწმებელი', fmt(k.awaiting_qc), 'ველმა უპასუხა', 'text-orange'),
      card('გასავლელი', fmt(k.pending), 'ჯერ შეუმოწმებელი'),
    ].join('');
  }

  function renderTrend(t) {
    const el = $('ch-trend');
    if (!chart || chart.getDom() !== el) chart = echarts.init(el, null, { renderer: 'canvas' });
    const mk = (name, key, color, top) => ({
      name, type: 'bar', stack: 'v', barMaxWidth: 26, data: t.map((d) => d[key]),
      itemStyle: { color, borderColor: '#fff', borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 },
      emphasis: { focus: 'series' },
    });
    const axis = { axisLine: { lineStyle: { color: C.axis } }, axisTick: { show: false },
      axisLabel: { color: C.muted, fontFamily: FONT } };
    chart.setOption({
      aria: { enabled: true },
      textStyle: { fontFamily: FONT, color: C.ink, fontSize: 12 },
      legend: { top: 0, left: 0, textStyle: { color: C.muted, fontFamily: FONT } },
      grid: { left: 8, right: 12, top: 34, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, textStyle: { fontFamily: FONT } },
      xAxis: Object.assign({ type: 'category', data: t.map((d) => d.label) }, axis),
      yAxis: Object.assign({ type: 'value', splitLine: { lineStyle: { color: C.grid } } }, axis),
      series: [mk('დადებითი', 'positive', C.pos), mk('რეკომენდაცია', 'recommendation', C.rec),
        mk('უარყოფითი', 'negative', C.neg, true)],
    }, true);
  }

  function renderCodes(rows) {
    const top = rows.filter((r) => r.negative || r.recommendation)
      .sort((a, b) => b.negative - a.negative).slice(0, 12);
    const max = Math.max(1, ...top.map((r) => r.negative));
    $('t-codes').innerHTML = `<table class="table table-vcenter card-table"><tbody>${top.map((r) => `
      <tr><td><div class="fw-medium">${esc(r.code)}</div><div class="text-muted small text-truncate" style="max-width:190px" title="${esc(r.name)}">${esc(r.name)}</div></td>
      <td class="bar-cell"><div class="d-flex align-items-center gap-2"><div class="progress progress-sm flex-fill">
        <div class="progress-bar ${r.severity === 'Critical' ? 'bg-red' : 'bg-orange'}" style="width:${Math.round(100 * r.negative / max)}%"></div></div>
        <span class="small">${fmt(r.negative)}</span></div></td></tr>`).join('')}</tbody></table>`;
  }

  function renderOperators(rows) {
    $('card-operators').hidden = false;
    const sorted = rows.slice().sort((a, b) => b.checked - a.checked);
    $('t-operators').innerHTML = `<table class="table table-vcenter card-table table-hover">
      <thead><tr><th>ოპერატორი</th><th class="text-end">შემოწმებული</th><th class="text-end">დადებითი</th>
      <th class="text-end">უარყოფითი</th><th class="text-end">რეკომენდაცია</th><th class="text-end">ხარვეზი %</th></tr></thead>
      <tbody>${sorted.map((r) => {
        const rate = r.checked ? 100 * r.negative / r.checked : 0;
        return `<tr><td>${esc(r.name)}</td><td class="text-end">${fmt(r.checked)}</td><td class="text-end">${fmt(r.positive)}</td>
        <td class="text-end">${fmt(r.negative)}</td><td class="text-end">${fmt(r.recommendation)}</td>
        <td class="text-end"><span class="badge ${rate >= 40 ? 'bg-red-lt' : rate >= 30 ? 'bg-orange-lt' : 'bg-green-lt'}">${pct(Math.round(rate * 10) / 10)}</span></td></tr>`;
      }).join('')}</tbody></table>`;
  }

  async function load() {
    try {
      const r = await fetch(`/api/stats?${params()}`, { headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      if (d.kpi) renderKpi(d.kpi);
      if (d.trend) renderTrend(d.trend);
      if (d.codes) renderCodes(d.codes);
      if (d.operators) renderOperators(d.operators);
    } catch (e) {
      $('kpis').innerHTML = `<div class="col-12"><div class="alert alert-danger">სტატისტიკა ვერ ჩაიტვირთა (${esc(e.message)}).</div></div>`;
    }
  }
  $('p-range').addEventListener('change', load);
  $('p-kind').addEventListener('change', load);
  load();
})();
