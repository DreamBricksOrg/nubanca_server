const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { IDBFactory, IDBKeyRange } = require("fake-indexeddb");

function loadHistory(indexedDB = new IDBFactory(), globals = {}) {
  const script = path.join(__dirname, "../../app/static/js/print_history.js");
  assert.ok(fs.existsSync(script), "O histórico compartilhado precisa ser implementado");
  const window = {};
  vm.runInNewContext(fs.readFileSync(script, "utf8"), {
    window, indexedDB, IDBKeyRange, setTimeout, clearTimeout, Date, ...globals,
  });
  return window.PrintHistory;
}

module.exports = { loadHistory };
