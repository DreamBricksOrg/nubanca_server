const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function createGalleryHarness(fetchResult = async () => ({
  ok: true, json: async () => ({ success: true, printed: true, message: "Imagem enviada para impressão" }),
})) {
  const requests = [];
  const statuses = [{ textContent: "" }, { textContent: "" }];
  const buttons = statuses.map((status, index) => ({
    disabled: false, textContent: "Imprimir", dataset: { key: `back-covers/sp/photo-${index}.png` },
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    closest: () => ({ querySelector: () => status }),
  }));
  const scriptPath = path.join(__dirname, "../app/static/js/photos.js");
  assert.ok(fs.existsSync(scriptPath), "A galeria precisa do script que aciona a impressão");
  vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), {
    document: {
      getElementById: () => ({ dataset: { printUrl: "/photos/print" } }),
      querySelectorAll: () => buttons,
    },
    fetch: async (url, options) => { requests.push({ url, ...options }); return fetchResult(); },
  });
  return { requests, statuses, buttons };
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
  finish({ ok: true, json: async () => ({ success: true, printed: true, message: "Enviada" }) });
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
