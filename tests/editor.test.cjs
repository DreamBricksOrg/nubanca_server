const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function createEditorHarness(response = { ok: true, json: async () => ({ page_url: "https://photos.test/view/edited.png" }) }) {
  const context2d = {
    save() {}, restore() {}, translate() {}, drawImage() {}, clearRect() {},
  };
  const elements = new Map();
  for (const id of ["canvas1", "canvas2", "saveImage", "qrcodeOnly", "loading", "editor"]) {
    elements.set(id, {
      style: {}, disabled: false, width: 200, height: 300, listeners: {},
      getContext: () => context2d,
      addEventListener(event, callback) { this.listeners[event] = callback; },
    });
  }
  const requests = [];
  const stored = new Map();
  const errors = [];
  let blobCallback;
  let blobCount = 0;
  const window = { location: { href: "/editor" }, addEventListener() {} };
  const sandbox = {
    document: {
      getElementById: (id) => elements.get(id),
      createElement: () => ({
        getContext: () => context2d,
        toBlob(callback) { blobCallback = callback; blobCount += 1; },
      }),
    },
    window,
    editor: elements.get("editor"),
    BASE_URL: "https://kiosk.test",
    coverImagePath: "/cover.png",
    Image: class { width = 400; height = 600; },
    localStorage: { getItem: () => "/photo.png", setItem: (key, value) => stored.set(key, value) },
    FormData, Blob,
    fetch: async (url, options) => { requests.push({ url, ...options }); return response; },
    console: { error: (...args) => errors.push(args), log() {} },
    setInterval, clearInterval,
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, "../app/static/js/editor.js"), "utf8"),
    sandbox,
  );
  return {
    elements, requests, stored, window, errors,
    get blobCount() { return blobCount; },
    async finishBlob(blob = new Blob(["image"], { type: "image/png" })) {
      await blobCallback(blob);
      await new Promise(setImmediate);
    },
  };
}

test("apenas qrcode uploads the collage without printing and opens its QR Code", async () => {
  const harness = createEditorHarness();
  const qrcodeButton = harness.elements.get("qrcodeOnly");
  assert.equal(typeof qrcodeButton.listeners.click, "function");
  qrcodeButton.listeners.click();
  assert.equal(qrcodeButton.disabled, true);
  assert.equal(harness.elements.get("saveImage").disabled, true);
  assert.equal(harness.elements.get("loading").style.display, "flex");
  await harness.finishBlob();
  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].url, "https://kiosk.test/print");
  assert.equal(harness.requests[0].method, "POST");
  assert.equal(harness.requests[0].body.get("print"), "false");
  assert.equal(harness.requests[0].body.get("image").name, "edited-image.png");
  assert.equal(harness.stored.get("qrcodeImagePath"), "https://photos.test/view/edited.png");
  assert.equal(harness.window.location.href, "https://kiosk.test/qrcode");
  assert.equal(harness.errors.length, 0);
});

test("Salvar keeps printing enabled", async () => {
  const harness = createEditorHarness();
  harness.elements.get("saveImage").listeners.click();
  await harness.finishBlob();
  assert.equal(harness.requests[0].body.get("print"), "true");
  assert.equal(harness.window.location.href, "https://kiosk.test/qrcode");
});

test("both actions share the duplicate submission guard", async () => {
  const harness = createEditorHarness();
  harness.elements.get("qrcodeOnly").listeners.click();
  harness.elements.get("saveImage").listeners.click();
  assert.equal(harness.blobCount, 1);
  await harness.finishBlob();
  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].body.get("print"), "false");
});

test("upload failure keeps the editor open and allows retry", async () => {
  const harness = createEditorHarness({ ok: false, status: 500 });
  harness.elements.get("qrcodeOnly").listeners.click();
  await harness.finishBlob();
  assert.equal(harness.window.location.href, "/editor");
  assert.equal(harness.stored.has("qrcodeImagePath"), false);
  assert.equal(harness.elements.get("saveImage").disabled, false);
  assert.equal(harness.elements.get("qrcodeOnly").disabled, false);
  assert.equal(harness.elements.get("loading").style.display, "none");
  assert.equal(harness.errors.length, 1);
  harness.elements.get("qrcodeOnly").listeners.click();
  await harness.finishBlob();
  assert.equal(harness.requests.length, 2);
});

test("failed canvas export never uploads or navigates", async () => {
  const harness = createEditorHarness();
  harness.elements.get("qrcodeOnly").listeners.click();
  await harness.finishBlob(null);
  assert.equal(harness.requests.length, 0);
  assert.equal(harness.window.location.href, "/editor");
  assert.equal(harness.elements.get("saveImage").disabled, false);
  assert.equal(harness.elements.get("qrcodeOnly").disabled, false);
  assert.equal(harness.elements.get("loading").style.display, "none");
  assert.equal(harness.errors.length, 1);
});
