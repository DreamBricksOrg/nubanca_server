const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { loadHistory } = require("./helpers/print_history.cjs");

function createGalleryHarness(fetchResult = async () => ({
  ok: true, json: async () => ({ success: true, printed: true, message: "Imagem enviada para impressão",
    photo_key: "back-covers/sp/photo-0.png", queued_at: "2026-10-31T12:00:00Z" }),
}), history = loadHistory()) {
  const requests = [];
  const statuses = [{ textContent: "" }, { textContent: "" }];
  const labels = [{ textContent: "" }, { textContent: "" }];
  const estimates = [{ textContent: "" }, { textContent: "" }];
  const warning = { textContent: "" };
  const events = {};
  const cards = statuses.map((status, index) => {
    const classes = new Set();
    return {
      classList: {
        toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
        contains: (name) => classes.has(name),
      },
      querySelector: (selector) => ({
        ".print-status": status, ".print-history-label": labels[index], ".print-estimate": estimates[index],
      })[selector],
    };
  });
  const buttons = statuses.map((status, index) => ({
    disabled: false, textContent: "Imprimir", dataset: { key: `back-covers/sp/photo-${index}.png` },
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    closest: () => cards[index],
  }));
  const estimateButtons = buttons.map((button) => ({ ...button, listeners: {} }));
  const scriptPath = path.join(__dirname, "../app/static/js/photos.js");
  assert.ok(fs.existsSync(scriptPath), "A galeria precisa do script que aciona a impressão");
  vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), {
    document: {
      body: { dataset: { printScope: "scope-sp" } },
      getElementById: (id) => id === "photo-gallery" ? { dataset: { printUrl: "/photos/print" } } : warning,
      querySelectorAll: (selector) => selector === ".print-photo" ? buttons : estimateButtons,
    },
    window: { PrintHistory: history, addEventListener: (name, callback) => { events[name] = callback; } },
    fetch: async (url, options) => { requests.push({ url, ...options }); return fetchResult(); },
  });
  return { requests, statuses, buttons, cards, labels, estimates, estimateButtons, warning, events, history };
}

test("Imprimir sends only the selected S3 key and shows success", async () => {
  const harness = createGalleryHarness();
  const button = harness.buttons[0];
  assert.equal(typeof button.listeners.click, "function");
  const pending = button.listeners.click();
  assert.equal(button.disabled, true);
  assert.equal(button.textContent, "Imprimindo...");
  assert.equal(harness.buttons[1].disabled, false);
  await pending;
  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].url, "/photos/print");
  assert.equal(harness.requests[0].method, "POST");
  assert.equal(harness.requests[0].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(harness.requests[0].body), { key: "back-covers/sp/photo-0.png" });
  assert.equal(harness.statuses[0].textContent, "Imagem enviada para impressão");
  assert.equal(harness.statuses[1].textContent, "");
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, "Imprimir");
});

test("repeated clicks do not send a second print while the first is pending", async () => {
  let finish;
  const harness = createGalleryHarness(() => new Promise((resolve) => { finish = resolve; }));
  const button = harness.buttons[0];
  const pending = button.listeners.click();
  await button.listeners.click();
  assert.equal(harness.requests.length, 1);
  finish({ ok: true, json: async () => ({ success: true, printed: true, message: "Enviada",
    photo_key: "back-covers/sp/photo-0.png", queued_at: "2026-10-31T12:00:00Z" }) });
  await pending;
  assert.equal(button.disabled, false);
});

test("printer errors show the server message and allow retry", async () => {
  const harness = createGalleryHarness(async () => ({
    ok: false, json: async () => ({ success: false, printed: false, message: "Impressão desabilitada" }),
  }));
  const button = harness.buttons[0];
  await button.listeners.click();
  assert.equal(harness.statuses[0].textContent, "Impressão desabilitada");
  assert.equal(button.disabled, false);
  await button.listeners.click();
  assert.equal(harness.requests.length, 2);
});

test("a failed print result is not presented as success even for HTTP 200", async () => {
  const harness = createGalleryHarness(async () => ({
    ok: true, json: async () => ({ success: false, printed: false }),
  }));
  await harness.buttons[0].listeners.click();
  assert.equal(harness.statuses[0].textContent, "Não foi possível imprimir a foto.");
  assert.equal(harness.buttons[0].disabled, false);
});

test("network and invalid JSON failures restore the print button", async () => {
  for (const fetchResult of [
    async () => { throw new Error("Falha de conexão"); },
    async () => ({ ok: false, json: async () => { throw new Error("Resposta inválida"); } }),
  ]) {
    const harness = createGalleryHarness(fetchResult);
    await harness.buttons[0].listeners.click();
    assert.notEqual(harness.statuses[0].textContent, "");
    assert.equal(harness.buttons[0].disabled, false);
    assert.equal(harness.buttons[0].textContent, "Imprimir");
  }
});

test("gallery persists accepted print and marks its card green", async () => {
  const harness = createGalleryHarness();
  await harness.buttons[0].listeners.click();
  const rows = await harness.history.list("scope-sp");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].key, "back-covers/sp/photo-0.png");
  assert.equal(harness.cards[0].classList.contains("is-printed"), true);
  assert.equal(harness.cards[1].classList.contains("is-printed"), false);
  assert.match(harness.labels[0].textContent, /Enviada à impressão/);
});

test("gallery restores editor print history after reload and on tab focus", async () => {
  const history = loadHistory();
  await history.record("scope-sp", "back-covers/sp/photo-0.png", "2026-10-31T12:00:00Z");
  const harness = createGalleryHarness(undefined, history);
  assert.equal(typeof harness.events.focus, "function");
  await harness.events.focus();
  assert.equal(harness.cards[0].classList.contains("is-printed"), true);
  await history.record("scope-sp", "back-covers/sp/photo-1.png", "2026-10-31T12:01:00Z");
  await harness.events.focus();
  assert.equal(harness.cards[1].classList.contains("is-printed"), true);
});

test("failed dispatch stays out of history and has no green outline", async () => {
  const harness = createGalleryHarness(async () => ({ ok: false, json: async () => ({ success: false, printed: false }) }));
  await harness.buttons[0].listeners.click();
  assert.equal((await harness.history.list("scope-sp")).length, 0);
  assert.equal(harness.cards[0].classList.contains("is-printed"), false);
});

test("storage failure warns but does not misreport or resend accepted print", async () => {
  const harness = createGalleryHarness(undefined, {
    list: async () => { throw new Error("Unavailable"); },
    record: async () => { throw new Error("QuotaExceeded"); },
  });
  await harness.buttons[0].listeners.click();
  assert.match(harness.statuses[0].textContent, /Imagem enviada/);
  assert.match(harness.statuses[0].textContent, /histórico/);
  assert.equal(harness.requests.length, 1);
  assert.equal(harness.cards[0].classList.contains("is-printed"), true);
  assert.equal(harness.buttons[0].disabled, false);
});

test("estimate button shows hypothetical time without printing or marking the photo", async () => {
  const harness = createGalleryHarness();
  assert.equal(typeof harness.estimateButtons[0].listeners.click, "function");
  await harness.estimateButtons[0].listeners.click();
  assert.match(harness.estimates[0].textContent, /Se enviada agora/);
  assert.equal(harness.requests.length, 0);
  assert.equal((await harness.history.list("scope-sp")).length, 0);
  assert.equal(harness.cards[0].classList.contains("is-printed"), false);
});

test("estimate for an accepted print never claims physical completion", async () => {
  const harness = createGalleryHarness();
  await harness.buttons[0].listeners.click();
  await harness.estimateButtons[0].listeners.click();
  assert.match(harness.estimates[0].textContent, /Previsão/);
  assert.doesNotMatch(harness.estimates[0].textContent, /Impressão concluída/);
});

test("focus refresh includes reprints from another tab even for a card printed here", async () => {
  const harness = createGalleryHarness();
  await harness.buttons[0].listeners.click();
  await harness.history.record("scope-sp", "back-covers/sp/photo-0.png", "2026-10-31T12:01:00Z");
  await harness.events.focus();
  assert.match(harness.labels[0].textContent, /2 envio/);
});

test("estimate shows file timestamp as reference and recovers from unavailable storage", async () => {
  const harness = createGalleryHarness();
  harness.estimateButtons[0].dataset.key = "back-covers/20261031_120305_abcd.png";
  await harness.estimateButtons[0].listeners.click();
  assert.match(harness.estimates[0].textContent, /31\/10\/2026 12:03:05/);
  const unavailable = createGalleryHarness(undefined, {
    list: async () => [],
    estimate: async () => { throw new Error("Unavailable"); },
  });
  await unavailable.estimateButtons[0].listeners.click();
  assert.match(unavailable.estimates[0].textContent, /histórico local indisponível/);
  assert.equal(unavailable.estimateButtons[0].disabled, false);
  assert.equal(unavailable.requests.length, 0);
});
