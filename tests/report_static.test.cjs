const test = require('node:test');
const assert = require('node:assert/strict');
const { aggregate, parseJsonl } = require('../static-report/report.js');

function row(message, timestamp, photo_id = null, location = 'rj') {
  return { message, timestamp, photo_id, location };
}

test('static report groups by Brasilia day and separates created covers from reprints', () => {
  const events = [
    row('imprimir_imagem_sucesso', '2026-10-31T13:00:00Z', 'A'), // 10:00 31st
    row('visualizar_foto_acessada', '2026-10-31T13:00:30Z', 'A'),
    row('visualizar_foto_acessada', '2026-10-31T13:00:31Z', 'A'),
    row('apenas_qrcode_gerado', '2026-11-01T02:59:30Z', 'B'), // 23:59 31st
    row('visualizar_foto_acessada', '2026-11-01T03:00:30Z', 'B'), // next day, 60s later
    row('imprimir_imagem_sucesso', '2026-11-01T12:59:00Z', 'C'), // 09:59 next day
    row('visualizar_foto_acessada', '2026-11-01T12:58:59Z', 'C'), // before generation
    row('reimprimir_imagem_sucesso', '2026-11-01T13:00:00Z'),
    row('apenas_qrcode_gerado', '2026-11-01T12:00:00Z', 'wrong', 'sp'),
    row('imprimir_imagem_sucesso', '2026-11-02T03:00:00Z', 'outside'),
  ];

  const result = aggregate(events, { start: '2026-10-31', end: '2026-11-01', location: 'rj' });

  assert.deepEqual(result.totals, { generated: 3, printed: 2, digital: 1,
    reprints: 1, views: 4, shares: 0, downloads: 0, removed: null });
  assert.deepEqual(result.days.map(day => [day.date, day.generated, day.printed,
    day.digital, day.reprints, day.printedOpened, day.digitalOpened]), [
    ['2026-10-31', 2, 1, 1, 0, 1, 1],
    ['2026-11-01', 1, 1, 0, 1, 0, 0],
  ]);
  assert.equal(result.hourly.length, 14);
  assert.deepEqual(result.hourly.filter(hour => hour.total), [
    { hour: 10, printed: 1, digital: 0, total: 1 },
    { hour: 23, printed: 0, digital: 1, total: 1 },
  ]);
  assert.equal(result.peakHour.hour, 10);
  assert.equal(result.outsideHours, 1);
});

test('static report rejects invalid ranges and fails on corrupt JSONL', () => {
  assert.throws(() => aggregate([], { start: '2026-11-02', end: '2026-11-01', location: 'sp' }));
  assert.throws(() => aggregate([], { start: '2026-10-01', end: '2026-11-02', location: 'sp' }));
  assert.throws(() => aggregate([], { start: '2026-11-01', end: '2026-11-01', location: 'elsewhere' }));
  assert.deepEqual(parseJsonl('\n{"timestamp":"2026-11-01T13:00:00Z","message":"apenas_qrcode_gerado","location":"sp","photo_id":null}\n').length, 1);
  assert.throws(() => parseJsonl('{bad json}'));
});

test('removed files count distinct generated photos in the selected Brasilia period and location', () => {
  const missing = (message, timestamp, photo_id, location) =>
    ({ ...row(message, timestamp, photo_id, location), removed: true });
  const result = aggregate([
    missing('imprimir_imagem_sucesso', '2026-11-01T17:57:45Z', 'removed-photo', 'rj'),
    missing('imprimir_imagem_sucesso', '2026-11-01T17:57:46Z', 'removed-photo', 'rj'),
    missing('reimprimir_imagem_sucesso', '2026-11-01T18:00:00Z', 'reprint', 'rj'),
    missing('apenas_qrcode_gerado', '2026-11-02T03:00:00Z', 'next-day', 'rj'),
    missing('apenas_qrcode_gerado', '2026-11-01T18:00:00Z', 'other-place', 'sp'),
    { ...row('apenas_qrcode_gerado', '2026-11-01T18:00:00Z', 'present', 'rj'), removed: false },
  ], { start: '2026-10-31', end: '2026-11-01', location: 'rj' });
  assert.equal(result.totals.generated, 3);
  assert.equal(result.totals.removed, 1);
});
