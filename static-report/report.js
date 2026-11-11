(function () {
  'use strict';

  const PRINT = 'imprimir_imagem_sucesso';
  const DIGITAL = 'apenas_qrcode_gerado';
  const REPRINT = 'reimprimir_imagem_sucesso';
  const VIEW = 'visualizar_foto_acessada';
  const SHARE = 'compartilhar_imagem';
  const DOWNLOAD = 'baixar_imagem';
  const DAY = 86400000;
  const HOUR = 3600000;
  const MINUTE = 60000;
  const EVENTS = new Set([PRINT, DIGITAL, REPRINT, VIEW, SHARE, DOWNLOAD]);
  const labels = [
    ['generated', 'Capas geradas', 'para impressão + apenas QR Code'],
    ['printed', 'Geradas para impressão', 'no período selecionado'],
    ['digital', 'Apenas QR Code', 'no período selecionado'],
    ['reprints', 'Reimpressões', 'não criam novas capas'],
    ['removed', 'Arquivos removidos', 'removidos do S3 por pedido do usuario'],
    ['views', 'Visualizações', 'no período selecionado'],
    ['shares', 'Compartilhamentos', 'no período selecionado'],
    ['downloads', 'Downloads', 'no período selecionado'],
  ];

  function parseJsonl(text) {
    return text.split(/\r?\n/).filter(line => line.trim()).map(line => JSON.parse(line));
  }

  function parseDay(day) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error('Data inválida.');
    const ms = Date.parse(day + 'T00:00:00Z');
    if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0, 10) !== day) {
      throw new Error('Data inválida.');
    }
    return ms;
  }

  function aggregate(rows, { start, end, location }) {
    if (!['sp', 'rj'].includes(location)) throw new Error('Escolha SP ou RJ.');
    const first = parseDay(start);
    const last = parseDay(end);
    if (first > last || last - first > 30 * DAY) throw new Error('Escolha um período de até 31 dias.');
    const startUtc = first + 3 * HOUR;
    const endUtc = last + DAY + 3 * HOUR;
    const days = [];
    const byDate = new Map();
    for (let day = first; day <= last; day += DAY) {
      const date = new Date(day).toISOString().slice(0, 10);
      const item = { date, generated: 0, printed: 0, digital: 0, reprints: 0,
        views: 0, shares: 0, downloads: 0, printedOpened: 0, digitalOpened: 0 };
      days.push(item);
      byDate.set(date, item);
    }
    const hourly = Array.from({ length: 14 }, (_, offset) => ({ hour: offset + 10,
      printed: 0, digital: 0, total: 0 }));
    const viewTimes = new Map();
    const generated = [];
    const removedPhotos = new Set();
    let missingStorageStatus = false;

    for (const row of rows) {
      if (!row || row.location !== location || !EVENTS.has(row.message)) continue;
      const when = Date.parse(row.timestamp);
      if (!Number.isFinite(when) || when < startUtc || when >= endUtc + MINUTE) continue;
      const local = new Date(when - 3 * HOUR);
      const date = local.toISOString().slice(0, 10);
      if (row.message === VIEW && row.photo_id && typeof row.photo_id === 'string') {
        if (!viewTimes.has(row.photo_id)) viewTimes.set(row.photo_id, []);
        viewTimes.get(row.photo_id).push(when);
      }
      if (when >= endUtc) continue; // A next-day view can complete the last day's QR flow.
      const day = byDate.get(date);
      if (!day) continue;
      const kind = row.message === PRINT ? 'printed' : row.message === DIGITAL ? 'digital'
        : row.message === REPRINT ? 'reprints' : row.message === VIEW ? 'views'
          : row.message === SHARE ? 'shares' : 'downloads';
      day[kind]++;
      if (kind === 'printed' || kind === 'digital') {
        day.generated++;
        if (typeof row.removed !== 'boolean' || !row.photo_id) missingStorageStatus = true;
        else if (row.removed) removedPhotos.add(row.photo_id);
        const hour = local.getUTCHours();
        if (hour >= 10 && hour <= 23) {
          hourly[hour - 10][kind]++;
          hourly[hour - 10].total++;
        }
        if (row.photo_id && typeof row.photo_id === 'string') {
          generated.push({ when, kind, photo: row.photo_id, date });
        }
      }
    }
    for (const times of viewTimes.values()) times.sort((a, b) => a - b);
    const seen = new Set();
    generated.sort((a, b) => a.when - b.when);
    for (const item of generated) {
      const key = item.kind + ':' + item.photo;
      if (seen.has(key)) continue;
      seen.add(key);
      const views = viewTimes.get(item.photo) || [];
      if (views.some(view => view >= item.when && view <= item.when + MINUTE)) {
        byDate.get(item.date)[item.kind === 'printed' ? 'printedOpened' : 'digitalOpened']++;
      }
    }
    const totals = { generated: 0, printed: 0, digital: 0, reprints: 0,
      views: 0, shares: 0, downloads: 0 };
    for (const day of days) for (const key of Object.keys(totals)) totals[key] += day[key];
    totals.removed = missingStorageStatus ? null : removedPhotos.size;
    const peakHour = hourly.reduce((best, item) => item.total > (best ? best.total : 0) ? item : best, null);
    const peakDay = days.reduce((best, item) => item.generated > (best ? best.generated : 0) ? item : best, null);
    return { totals, days, hourly, peakHour, peakDay,
      outsideHours: totals.generated - hourly.reduce((sum, hour) => sum + hour.total, 0) };
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { aggregate, parseJsonl };
  if (typeof document === 'undefined') return;

  const number = value => new Intl.NumberFormat('pt-BR').format(value);
  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function renderBars(target, rows, peak, daily) {
    target.replaceChildren();
    target.style.minWidth = daily ? `${Math.max(720, rows.length * 42)}px` : '760px';
    if (daily) target.style.setProperty('--day-columns', rows.length);
    const max = Math.max(1, ...rows.map(row => daily ? row.generated : row.total));
    for (const row of rows) {
      const item = node('div', 'bar-chart-item');
      const total = daily ? row.generated : row.total;
      item.dataset[daily ? 'day' : 'hour'] = daily ? row.date : row.hour;
      Object.assign(item.dataset, { printed: row.printed, digital: row.digital, count: total });
      item.setAttribute('role', 'group');
      item.setAttribute('aria-label', `${daily ? row.date : String(row.hour).padStart(2, '0') + ':00'}: ${row.printed} para impressão, ${row.digital} apenas QR Code`);
      item.append(node('span', 'bar-total', String(total)));
      const track = node('div', 'bar-track');
      track.setAttribute('aria-hidden', 'true');
      for (const [kind, style] of [['printed', 'bar-printed'], ['digital', 'bar-digital']]) {
        const bar = node('span', `bar-segment ${style}`);
        bar.style.height = row[kind] ? `${Math.max(1, Math.round(100 * row[kind] / max))}%` : '0%';
        track.append(bar);
      }
      item.append(track);
      item.append(node('span', 'bar-label', daily ? row.date.slice(8) + '/' + row.date.slice(5, 7)
        : String(row.hour).padStart(2, '0') + 'h'));
      target.append(item);
    }
  }
  function render(result, start, end, location) {
    document.getElementById('date-pill').textContent = `${location.toUpperCase()} · ${start} → ${end}`;
    const cards = document.getElementById('cards');
    cards.replaceChildren();
    const icons = ['▣', '↗', '▦', '⟳', '✕', '◉', '⇪', '↓'];
    labels.forEach(([key, label, foot], index) => {
      const card = node('article', `card card-${index + 1}`);
      if (result.totals[key] !== null) card.dataset.count = result.totals[key];
      card.append(node('span', 'card-icon', icons[index]), node('span', 'card-label', label),
        node('strong', '', result.totals[key] === null ? '—' : number(result.totals[key])),
        node('span', 'card-foot', result.totals[key] === null ? 'reexporte o snapshot para atualizar' : foot));
      cards.append(card);
    });
    renderBars(document.getElementById('hourly-bars'), result.hourly, result.peakHour, false);
    renderBars(document.getElementById('daily-bars'), result.days, result.peakDay, true);
    document.getElementById('hourly-peak').textContent = result.peakHour
      ? `Pico: ${String(result.peakHour.hour).padStart(2, '0')}:00 · ${number(result.peakHour.total)} capas` : '';
    document.getElementById('daily-peak').textContent = result.peakDay
      ? `Dia mais movimentado: ${result.peakDay.date.slice(8)}/${result.peakDay.date.slice(5, 7)} · ${number(result.peakDay.generated)} capas` : '';
    document.getElementById('outside-hours').textContent = ``;
    const tbody = document.getElementById('daily-rows');
    tbody.replaceChildren();
    for (const day of [...result.days].reverse()) {
      const row = node('tr');
      row.append(node('th', '', day.date));
      for (const key of ['generated', 'printed', 'digital', 'reprints', 'views', 'shares', 'downloads', 'printedOpened', 'digitalOpened']) {
        row.append(node('td', '', number(day[key])));
      }
      tbody.append(row);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const error = document.getElementById('report-error');
    const form = document.getElementById('filters');
    let events;
    try {
      const response = await fetch('logs.jsonl', { cache: 'no-store' });
      if (!response.ok) throw new Error('Não foi possível carregar o arquivo logs.jsonl.');
      events = parseJsonl(await response.text());
      error.textContent = '';
    } catch (err) {
      error.textContent = err.message || 'Arquivo de dados inválido.';
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const today = new Date(Date.now() - 3 * HOUR).toISOString().slice(0, 10);
    form.elements.inicio.value = params.get('inicio') || new Date(parseDay(today) - 6 * DAY).toISOString().slice(0, 10);
    form.elements.fim.value = params.get('fim') || today;
    form.elements.event_location.value = params.get('event_location') || 'sp';
    function update() {
      try {
        const start = form.elements.inicio.value;
        const end = form.elements.fim.value;
        const location = form.elements.event_location.value;
        render(aggregate(events, { start, end, location }), start, end, location);
        error.textContent = '';
        const search = new URLSearchParams({ inicio: start, fim: end, event_location: location });
        history.replaceState(null, '', `?${search}`);
      } catch (err) {
        error.textContent = err.message || 'Não foi possível gerar o relatório.';
      }
    }
    form.addEventListener('submit', event => { event.preventDefault(); update(); });
    update();
  });
})();
