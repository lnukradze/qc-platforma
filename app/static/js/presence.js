/* „ვინ ხსნის ოქმს ახლა" — ყვითელი ნელა მოციმციმე ნიშანი სიაში და ბარათზე.
   ბარათი ყოველ 20 წამში აგზავნის სიგნალს; სია ყოველ 20 წამში კითხულობს, რომელ ოქმებს ხსნის სხვა.
   ორი ამზომველის ერთდროულობისას: ვინც პირველი გაგზავნის, იმისი პასუხი ითვლება (სერვერი ამოწმებს). */
(function () {
  'use strict';
  const EVERY = 20000;

  function paint(el, people) {
    if (!el) return;
    if (!people || !people.length) { el.hidden = true; return; }
    const who = people.map(function (p) { return p.name + (p.role ? ' (' + p.role + ')' : ''); }).join(', ');
    el.hidden = false;
    el.title = 'ახლა ხსნის: ' + who;
    const label = el.querySelector('.presence-who');
    if (label) label.textContent = 'ახლა ხსნის: ' + who;
  }

  // ── ბარათი ──
  const self = document.querySelector('[data-presence][data-self]');
  if (self) {
    const id = self.dataset.presence;
    const ping = function () {
      fetch('/api/presence/' + id, { method: 'POST', credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d) paint(self, d.others); })
        .catch(function () {});
    };
    ping();
    setInterval(ping, EVERY);
    window.addEventListener('pagehide', function () {
      try { navigator.sendBeacon('/api/presence/' + id + '/leave'); } catch (e) { /* არაფერი */ }
    });
    return;
  }

  // ── სია ──
  function poll() {
    const marks = document.querySelectorAll('[data-presence]');
    if (!marks.length) return;
    const ids = Array.prototype.map.call(marks, function (m) { return m.dataset.presence; });
    fetch('/api/presence?ids=' + ids.join(','), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { marks.forEach(function (m) { paint(m, d[m.dataset.presence]); }); })
      .catch(function () {});
  }
  poll();
  setInterval(poll, EVERY);
  document.body.addEventListener('htmx:afterSwap', poll);
})();
