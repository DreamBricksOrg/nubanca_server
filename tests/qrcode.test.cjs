const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function qrText(hash, storage) {
  let text;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../app/static/js/qrcode.js"), "utf8"), {
    document: { getElementById: () => ({}) },
    window: { location: { hash, href: "/qrcode" } },
    localStorage: storage,
    URLSearchParams,
    QRCode: function (element, options) { text = options.text; },
    BASE_URL: "https://kiosk.test", TIMEOUT: 30,
    setTimeout() {},
  });
  return text;
}

test("QR Code uses the current fallback link even when localStorage is unavailable or stale", () => {
  const url = "https://photos.test/view/current.png";
  const hash = "#image=" + encodeURIComponent(url);
  assert.equal(qrText(hash, { getItem() { throw new Error("SecurityError"); } }), url);
  assert.equal(qrText(hash, { getItem: () => "https://photos.test/view/old.png" }), url);
});

test("QR Code preserves the normal localStorage flow", () => {
  assert.equal(qrText("", { getItem: () => "https://photos.test/view/stored.png" }), "https://photos.test/view/stored.png");
});
