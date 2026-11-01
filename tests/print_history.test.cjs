const assert = require("node:assert/strict");
const test = require("node:test");
const { IDBFactory, IDBObjectStore, IDBIndex, IDBCursor } = require("fake-indexeddb");
const { loadHistory } = require("./helpers/print_history.cjs");

const start = Date.parse("2026-10-31T12:00:00-03:00");
const firstKey = "back-covers/sp/20261031_120000_abcd.png";

test("persists photo names and queue timing across page loads", async () => {
  const db = new IDBFactory();
  const history = loadHistory(db);
  const row = await history.record("printer-sp", firstKey, new Date(start).toISOString());
  assert.equal(row.filename, "20261031_120000_abcd.png");
  assert.equal(row.queuedAt, start);
  assert.equal(row.readyAt, start + 210000);
  assert.equal(row.printCount, 1);
  const reloaded = loadHistory(db);
  const rows = await reloaded.list("printer-sp");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].key, firstKey);
  assert.equal(rows[0].readyAt, start + 210000);
  assert.equal((await reloaded.list("other-printer")).length, 0);
});

test("queue estimates serialize consecutive prints and count reprints", async () => {
  const history = loadHistory();
  await history.record("sp", firstKey, new Date(start).toISOString());
  const second = await history.record("sp", "back-covers/sp/second.png", new Date(start + 10000).toISOString());
  assert.equal(second.readyAt, start + 420000);
  const reprint = await history.record("sp", firstKey, new Date(start + 20000).toISOString());
  assert.equal(reprint.readyAt, start + 630000);
  assert.equal(reprint.printCount, 2);
  assert.equal((await history.list("sp")).length, 2);
  const estimate = await history.estimate("sp", firstKey, start + 30000);
  assert.equal(estimate.recorded, true);
  assert.equal(estimate.readyAt, start + 630000);
  assert.equal(estimate.remainingMs, 600000);
});

test("hypothetical estimate uses next queue slot but never marks an unprinted photo", async () => {
  const history = loadHistory();
  await history.record("sp", firstKey, new Date(start).toISOString());
  const estimate = await history.estimate("sp", "back-covers/20200101_010203_old.png", start + 10000);
  assert.equal(estimate.recorded, false);
  assert.equal(estimate.readyAt, start + 420000);
  assert.equal((await history.list("sp")).length, 1);
  const later = await history.estimate("sp", "unprinted.png", start + 1000000);
  assert.equal(later.readyAt, start + 1000000 + 210000);
});

test("completed estimates remain estimates and idle queues restart at a new dispatch", async () => {
  const history = loadHistory();
  await history.record("sp", firstKey, new Date(start).toISOString());
  const estimate = await history.estimate("sp", firstKey, start + 300000);
  assert.equal(estimate.remainingMs, 0);
  const row = await history.record("sp", firstKey, new Date(start + 600000).toISOString());
  assert.equal(row.readyAt, start + 600000 + 210000);
});

test("concurrent tabs cannot overwrite queue progress", async () => {
  const db = new IDBFactory();
  const first = loadHistory(db);
  const second = loadHistory(db);
  const rows = await Promise.all([
    first.record("sp", firstKey, new Date(start).toISOString()),
    second.record("sp", "second.png", new Date(start).toISOString()),
    first.record("sp", "third.png", new Date(start).toISOString()),
  ]);
  assert.deepEqual(rows.map((row) => row.readyAt).sort(), [start + 210000, start + 420000, start + 630000]);
  assert.equal((await second.list("sp")).length, 3);
});

test("reversed same-photo responses retain newest metadata and all reprints after reload", async () => {
  const db = new IDBFactory();
  const newest = start + 600000;
  await loadHistory(db).record("sp", firstKey, new Date(newest).toISOString());
  const row = await loadHistory(db).record("sp", firstKey, new Date(start).toISOString());
  assert.equal(row.queuedAt, newest);
  assert.equal(row.readyAt, newest + 210000);
  assert.equal(row.printCount, 2);
  const [persisted] = await loadHistory(db).list("sp");
  assert.equal(persisted.queuedAt, newest);
  assert.equal(persisted.readyAt, newest + 210000);
  assert.equal(persisted.printCount, 2);
});

test("delayed earlier response with an idle gap does not inflate the newer queue", async () => {
  const db = new IDBFactory();
  const history = loadHistory(db);
  await history.record("sp", "newer.png", new Date(start + 600000).toISOString());
  const older = await history.record("sp", firstKey, new Date(start).toISOString());
  assert.equal(older.readyAt, start + 210000);
  const reloaded = loadHistory(db);
  assert.equal((await reloaded.estimate("sp", "newer.png", start)).readyAt, start + 810000);
  assert.equal((await reloaded.estimate("sp", "unprinted.png", start)).readyAt, start + 1020000);
  assert.equal((await reloaded.list("sp")).length, 2);
});

test("delayed busy-overlap responses replay later predictions atomically across tabs", async () => {
  const db = new IDBFactory();
  const first = loadHistory(db);
  const second = loadHistory(db);
  await first.record("sp", "later.png", new Date(start + 60000).toISOString());
  await first.record("sp", "last.png", new Date(start + 120000).toISOString());
  await Promise.all([
    second.record("sp", firstKey, new Date(start).toISOString()),
    first.record("sp", "later.png", new Date(start + 30000).toISOString()),
  ]);
  const reloaded = loadHistory(db);
  const rows = await reloaded.list("sp");
  assert.equal(rows.find((row) => row.key === firstKey).readyAt, start + 210000);
  const later = rows.find((row) => row.key === "later.png");
  assert.equal(later.queuedAt, start + 60000);
  assert.equal(later.readyAt, start + 630000);
  assert.equal(later.printCount, 2);
  assert.equal(rows.find((row) => row.key === "last.png").readyAt, start + 840000);
  assert.equal((await reloaded.estimate("sp", "next.png", start)).readyAt, start + 1050000);
});

test("forecast is chronological for varied arrival orders, tied dispatches and reprints", async () => {
  const dispatches = [
    { key: "a.png", offset: 0 }, { key: "b.png", offset: 60000 },
    { key: "a.png", offset: 60000 }, { key: "c.png", offset: 120000 },
    { key: "a.png", offset: 1500000 }, { key: "b.png", offset: 1560000 },
  ];
  const orders = [
    [0, 1, 2, 3, 4, 5], [5, 4, 3, 2, 1, 0], [3, 0, 5, 1, 4, 2],
    [4, 2, 0, 5, 1, 3], [1, 3, 5, 0, 2, 4], [2, 1, 5, 4, 0, 3],
  ];
  for (const order of orders) {
    const db = new IDBFactory();
    const history = loadHistory(db);
    await history.record("other-scope", "unrelated.png", new Date(start + 9999999).toISOString());
    const accepted = [];
    for (const index of order) {
      const job = dispatches[index];
      await history.record("sp", job.key, new Date(start + job.offset).toISOString());
      accepted.push(job);
    }
    let tail = 0;
    const expected = new Map();
    for (const job of accepted.toSorted((a, b) => a.offset - b.offset)) {
      tail = Math.max(start + job.offset, tail) + 210000;
      expected.set(job.key, {
        queuedAt: start + job.offset, readyAt: tail,
        printCount: (expected.get(job.key)?.printCount || 0) + 1,
      });
    }
    for (const row of await loadHistory(db).list("sp")) {
      assert.deepEqual({ queuedAt: row.queuedAt, readyAt: row.readyAt, printCount: row.printCount }, expected.get(row.key));
    }
    assert.equal((await history.estimate("sp", "next.png", start)).readyAt, tail + 210000);
    assert.equal((await history.list("other-scope"))[0].printCount, 1);
  }
});

test("normal append skips replay and delayed replay stops at an idle gap", async (t) => {
  const history = loadHistory();
  await history.record("sp", "busy.png", new Date(start + 60000).toISOString());
  await history.record("sp", "idle.png", new Date(start + 600000).toISOString());
  const scan = t.mock.method(IDBIndex.prototype, "openCursor");
  const updates = t.mock.method(IDBCursor.prototype, "update");
  await history.record("sp", "tail.png", new Date(start + 610000).toISOString());
  assert.equal(scan.mock.callCount(), 0, "chronological append must not scan old jobs");
  await history.record("sp", firstKey, new Date(start).toISOString());
  assert.equal(updates.mock.callCount(), 1, "only the busy job changes; idle and later jobs are untouched");
  assert.equal((await history.estimate("sp", "tail.png", start)).readyAt, start + 1020000);
});

test("an aborted delayed replay rolls back dispatches, summaries, counts and queue", async (t) => {
  const db = new IDBFactory();
  const history = loadHistory(db);
  await history.record("sp", "later.png", new Date(start + 60000).toISOString());
  t.mock.method(IDBCursor.prototype, "update", function () {
    this.source.objectStore.transaction.abort();
    return {};
  });
  await assert.rejects(history.record("sp", firstKey, new Date(start).toISOString()));
  const rows = await loadHistory(db).list("sp");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].key, "later.png");
  assert.equal(rows[0].printCount, 1);
  assert.equal(rows[0].readyAt, start + 270000);
  assert.equal((await history.estimate("sp", "next.png", start)).readyAt, start + 480000);
  t.mock.restoreAll();
  await history.record("sp", firstKey, new Date(start).toISOString());
  assert.equal((await history.estimate("sp", "later.png", start)).readyAt, start + 420000);
});

async function seedVersionOne(db, rows = []) {
  await new Promise((resolve, reject) => {
    const request = db.open("nubanca-print-history", 1);
    request.onupgradeneeded = () => {
      const photos = request.result.createObjectStore("photos", { keyPath: ["scope", "key"] });
      photos.createIndex("scope", "scope");
      const queues = request.result.createObjectStore("queues", { keyPath: "scope" });
      for (const row of rows) photos.put(row);
      if (rows.length) queues.put({ scope: "sp", readyAt: Math.max(...rows.map((row) => row.readyAt)) });
    };
    request.onerror = () => reject(request.error);
    request.onsuccess = () => { request.result.close(); resolve(); };
  });
}

test("version-one migration preserves green history, counts and conservative queue anchors", async () => {
  const db = new IDBFactory();
  const newest = start + 600000;
  await seedVersionOne(db, [{
    scope: "sp", key: firstKey, filename: firstKey.split("/").pop(),
    queuedAt: newest, readyAt: newest + 420000, printCount: 3,
  }]);
  const history = loadHistory(db);
  assert.equal((await history.list("sp"))[0].printCount, 3);
  const row = await history.record("sp", firstKey, new Date(start).toISOString());
  assert.equal(row.queuedAt, newest);
  assert.equal(row.readyAt, newest + 420000);
  assert.equal(row.printCount, 4);
  const reloaded = loadHistory(db);
  assert.equal((await reloaded.list("sp"))[0].printCount, 4);
  assert.equal((await reloaded.estimate("sp", "next.png", start)).readyAt, newest + 630000);
});

test("migration reconciles reversed legacy anchors without reducing saved forecasts", async () => {
  const db = new IDBFactory();
  await seedVersionOne(db, [
    { scope: "sp", key: "older.png", filename: "older.png", queuedAt: start,
      readyAt: start + 1020000, printCount: 2 },
    { scope: "sp", key: "newer.png", filename: "newer.png", queuedAt: start + 600000,
      readyAt: start + 810000, printCount: 1 },
  ]);
  const history = loadHistory(db);
  const rows = await history.list("sp");
  assert.equal(rows.find((row) => row.key === "older.png").readyAt, start + 1020000);
  assert.equal(rows.find((row) => row.key === "newer.png").readyAt, start + 1230000);
  assert.equal(rows.reduce((sum, row) => sum + row.printCount, 0), 3);
  assert.equal((await history.estimate("sp", "next.png", start)).readyAt, start + 1440000);
});

test("empty version-one database upgrades without losing the first dispatch", async () => {
  const db = new IDBFactory();
  await seedVersionOne(db);
  const row = await loadHistory(db).record("sp", firstKey, new Date(start).toISOString());
  assert.equal(row.readyAt, start + 210000);
  assert.equal((await loadHistory(db).list("sp")).length, 1);
});

test("storage unavailability and invalid metadata reject instead of fabricating history", async () => {
  await assert.rejects(loadHistory(null).list("sp"), /indisponível/);
  const history = loadHistory();
  await assert.rejects(history.record("sp", firstKey, "invalid"), /inválidos/);
  assert.equal((await history.list("sp")).length, 0);
});

test("filename date is a reference, not the enqueue time", async () => {
  const history = loadHistory();
  assert.equal(history.fileTime("back-covers/sp/20261031_120305_abcd.png"), "31/10/2026 12:03:05");
  assert.equal(history.fileTime("20260230_120305_bad.png"), null);
  assert.equal(history.fileTime("not-a-timestamp.png"), null);
  const row = await history.record("sp", "20200101_010203_old.png", new Date(start).toISOString());
  assert.equal(row.queuedAt, start);
  assert.equal(row.readyAt, start + 210000);
});

test("aborted writes cannot leave a photo marked without its queue update", async (t) => {
  const history = loadHistory();
  const put = IDBObjectStore.prototype.put;
  t.mock.method(IDBObjectStore.prototype, "put", function (...args) {
    if (this.name === "queues") {
      this.transaction.abort();
      return {};
    }
    return put.apply(this, args);
  });
  await assert.rejects(history.record("sp", firstKey, new Date(start).toISOString()));
  assert.equal((await history.list("sp")).length, 0);
  const estimate = await history.estimate("sp", firstKey, start);
  assert.equal(estimate.readyAt, start + 210000);
});

test("browser security denial releases the pending open timer", async () => {
  let timers = 0;
  const history = loadHistory({ open() { throw new Error("SecurityError"); } }, {
    setTimeout() { timers += 1; return 1; },
    clearTimeout() { timers -= 1; },
  });
  await assert.rejects(history.list("sp"), /SecurityError/);
  assert.equal(timers, 0);
});
