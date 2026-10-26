/* status_banner.js - riga "Ultimo controllo" nella testata.
   Viene incollato in index.html da inject_data.py (blocco STATO-INIZIO/FINE).
   Legge status.json se raggiungibile, altrimenti usa window.RICHIAMI_STATUS. */
(function () {
  var STALE_DAYS = 5; // lo scraper gira lun e gio: il vuoto massimo previsto e' 4 giorni
  var app = document.getElementById('app');
  if (!app) return;

  var fmt = new Intl.DateTimeFormat('it-IT', {
    timeZone: 'Europe/Rome', weekday: 'short', day: 'numeric', month: 'short',
    year: 'numeric', hour: '2-digit', minute: '2-digit'
  });

  var style = document.createElement('style');
  style.textContent =
    '.update-line{margin-top:10px;font-size:12.5px;color:var(--ink-soft)}' +
    '.update-main{color:var(--ink);font-weight:600}' +
    '.update-note{margin-top:2px}' +
    '.update-warn{margin-top:8px;padding:8px 10px;background:var(--alert-soft);' +
    'color:var(--alert);border-left:3px solid var(--alert)}';
  document.head.appendChild(style);

  function isValid(s) { return s && typeof s === 'object' && typeof s.outcome === 'string'; }
  function ts(s) { return s && s.lastRunAt ? Date.parse(s.lastRunAt) || 0 : 0; }

  function load() {
    var embedded = isValid(window.RICHIAMI_STATUS) ? window.RICHIAMI_STATUS : null;
    return fetch('status.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (live) {
        if (!isValid(live)) return embedded;
        return embedded && ts(embedded) > ts(live) ? embedded : live;
      })
      .catch(function () { return embedded; });
  }

  function line(cls, text) {
    var el = document.createElement('div');
    el.className = cls;
    el.textContent = text;
    return el;
  }

  function build(s) {
    var box = document.createElement('div');
    box.className = 'update-line';
    var okTime = s.lastSuccessAt ? Date.parse(s.lastSuccessAt) : NaN;
    var hasOk = !isNaN(okTime);

    box.appendChild(line('update-main', hasOk
      ? 'Ultimo controllo: ' + fmt.format(new Date(okTime))
      : 'Nessun controllo completo registrato'));
    box.appendChild(line('update-note',
      'Ricerca di nuovi richiami il lunedì e il giovedì. Dati non in tempo reale.'));

    var ageDays = hasOk ? Math.floor((Date.now() - okTime) / 86400000) : null;
    if (ageDays !== null && ageDays > STALE_DAYS) {
      box.appendChild(line('update-warn',
        'Dati non aggiornati da ' + ageDays + ' giorni: la ricerca automatica potrebbe essere interrotta.'));
    } else if (s.outcome === 'partial' && s.lastRunAt) {
      box.appendChild(line('update-warn',
        'Il tentativo del ' + fmt.format(new Date(s.lastRunAt)) +
        ' è stato incompleto: alcuni richiami recenti potrebbero mancare.'));
    }
    return box;
  }

  var status = null;
  function apply() {
    if (!status) return;
    var stat = app.querySelector('.stat-line');
    if (!stat || app.querySelector('.update-line')) return;
    stat.insertAdjacentElement('afterend', build(status));
  }

  new MutationObserver(apply).observe(app, { childList: true, subtree: true });
  load().then(function (s) { status = s; apply(); });
})();
