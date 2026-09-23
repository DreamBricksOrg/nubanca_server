const canvas1 = document.getElementById("canvas1");
const canvas2 = document.getElementById("canvas2");

const input_up = document.getElementById("input_up");
const input_down = document.getElementById("input_bottom");
const input_left = document.getElementById("input_left");
const input_right = document.getElementById("input_right");

const input_zoom_in = document.getElementById("zoom_in");
const input_zoom_out = document.getElementById("zoom_out");

const saveImage_btn = document.getElementById("saveImage");

const moveSpeed = 5;

const ctx1 = canvas1.getContext("2d");
const ctx2 = canvas2.getContext("2d");

const img1 = new Image();
const img2 = new Image();

let image2Height = 0;
let zoom = 1;
let displayScale = 1;
let moveInterval = null;
let testPinch = false;
let virtualPointerId = "virtual";
let lastMouseX = 0;
let lastMouseY = 0;

img1.src = img1Path;
img2.src = img2Path;

let x = 0;
let y = 0;

let startX = 0;
let startY = 0;

let startPointerX = 0;
let startPointerY = 0;

const pointers = new Map();
let pinchStartDistance = 0;
let pinchStartZoom = 1;

function getDisplayScale() {
  const horizontalSpace = window.innerWidth * 0.8;

  const verticalSpace = window.innerHeight - 380; // space for arrows, zoom and footer

  const scaleX = horizontalSpace / img1.width;
  const scaleY = verticalSpace / img1.height;

  return Math.min(scaleX, scaleY);
}

// IMAGE 1
img1.onload = () => {
  displayScale = getDisplayScale();
  canvas1.width = img1.width * displayScale;
  canvas1.height = img1.height * displayScale;

  ctx1.drawImage(img1, 0, 0, canvas1.width, canvas1.height);
  setupEditor();
};

// IMAGE 2
img2.onload = () => {
  displayScale = getDisplayScale();

  canvas2.width = img1.width * displayScale;
  canvas2.height = img1.height * displayScale;

  const scale = canvas2.width / img2.width;

  image2Height = img2.height * scale;

  x = canvas2.width / 2;
  y = canvas2.height / 2;

  drawImage2();
  setupEditor();
};

function drawImage2() {
  ctx2.clearRect(0, 0, canvas2.width, canvas2.height);

  const width = canvas2.width * zoom;
  const height = image2Height * zoom;

  ctx2.save();

  ctx2.translate(x, y);

  ctx2.drawImage(img2, -width / 2, -height / 2, width, height);

  ctx2.restore();
}

function setupEditor() {
  if (!img1.complete || !img2.complete) return;

  const editor = document.getElementById("editor");

  editor.style.width = canvas1.width + "px";
  editor.style.height = canvas1.height + "px";
}

function startMoving(dx, dy) {
  if (moveInterval) return;

  moveImage(dx, dy);

  moveInterval = setInterval(() => {
    moveImage(dx, dy);
  }, 100);
}

function stopMoving() {
  clearInterval(moveInterval);
  moveInterval = null;
}

function moveImage(dx, dy) {
  x += dx;
  y += dy;

  drawImage2();
}

function saveImage() {
  const outputCanvas = document.createElement("canvas");

  outputCanvas.width = img1.width;
  outputCanvas.height = img1.height;

  const ctx = outputCanvas.getContext("2d");

  // Draw Image 2
  const originalX = x / displayScale;
  const originalY = y / displayScale;

  const originalWidth = (canvas2.width * zoom) / displayScale;
  const originalHeight = (image2Height * zoom) / displayScale;

  ctx.save();

  ctx.translate(originalX, originalY);

  ctx.drawImage(
    img2,
    -originalWidth / 2,
    -originalHeight / 2,
    originalWidth,
    originalHeight,
  );

  ctx.restore();

  // Draw Image 1 on top
  ctx.drawImage(img1, 0, 0, img1.width, img1.height);

  // Download
  const link = document.createElement("a");

  link.download = "edited-image.png";
  link.href = outputCanvas.toDataURL("image/png");

  link.click();
}

//#region screen display
window.addEventListener("resize", () => {
  if (!img1.complete || !img2.complete) return;

  displayScale = getDisplayScale();

  canvas1.width = img1.width * displayScale;
  canvas1.height = img1.height * displayScale;

  ctx1.drawImage(img1, 0, 0, canvas1.width, canvas1.height);

  canvas2.width = canvas1.width;
  canvas2.height = canvas1.height;

  const scale = canvas2.width / img2.width;

  image2Height = img2.height * scale;

  drawImage2();
  setupEditor();
});
//#endregion

//#region buttons

input_up.addEventListener("mousedown", () => {
  startMoving(0, -moveSpeed);
});

input_down.addEventListener("mousedown", () => {
  startMoving(0, moveSpeed);
});

input_left.addEventListener("mousedown", () => {
  startMoving(-moveSpeed, 0);
});

input_right.addEventListener("mousedown", () => {
  startMoving(moveSpeed, 0);
});

input_zoom_in.addEventListener("click", () => {
  zoom += 0.1;
  drawImage2();
});

window.addEventListener("mouseup", stopMoving);

input_zoom_out.addEventListener("click", () => {
  zoom = Math.max(0.1, zoom - 0.1);
  drawImage2();
});

saveImage_btn.addEventListener("click", () => {
  saveImage();
});
//#endregion

//#region pointer

editor.addEventListener("pointerdown", (e) => {
  pointers.set(e.pointerId, {
    x: e.clientX,
    y: e.clientY,
  });

  canvas2.setPointerCapture(e.pointerId);

  if (pointers.size === 1) {
    startPointerX = e.clientX;
    startPointerY = e.clientY;

    startX = x;
    startY = y;
  }
  if (pointers.size === 2) {
    const [p1, p2] = [...pointers.values()];

    pinchStartDistance = Math.hypot(p2.x - p1.x, p2.y - p1.y);

    pinchStartZoom = zoom;
  }
});

editor.addEventListener("pointermove", (e) => {
  if (!pointers.has(e.pointerId)) return;

  pointers.set(e.pointerId, {
    x: e.clientX,
    y: e.clientY,
  });
  if (pointers.size === 1) {
    const rect = canvas2.getBoundingClientRect();

    // Convert screen movement to canvas coordinates
    const scaleX = canvas2.width / rect.width;
    const scaleY = canvas2.height / rect.height;

    const dx = (e.clientX - startPointerX) * scaleX;
    const dy = (e.clientY - startPointerY) * scaleY;

    x = startX + dx;
    y = startY + dy;

    drawImage2();
    return;
  }
  if (pointers.size === 2) {
    const [p1, p2] = [...pointers.values()];

    const currentDistance = Math.hypot(p2.x - p1.x, p2.y - p1.y);

    if (pinchStartDistance === 0) return;

    const ratio = currentDistance / pinchStartDistance;

    zoom = Math.max(0.1, pinchStartZoom * ratio);

    drawImage2();
  }
});

editor.addEventListener("pointerup", (e) => {
  pointers.delete(e.pointerId);
  if (pointers.size === 1) {
    const [p] = [...pointers.values()];

    // Restart movement from
    // the current image position

    startPointerX = p.x;
    startPointerY = p.y;

    startX = x;
    startY = y;
  }

  // =========================
  // NO POINTERS
  // =========================

  if (pointers.size === 0) {
    pinchStartDistance = 0;
  }

  if (canvas2.hasPointerCapture(e.pointerId)) {
    canvas2.releasePointerCapture(e.pointerId);
  }
});

editor.addEventListener("pointercancel", (e) => {
  pointers.delete(e.pointerId);

  if (pointers.size === 1) {
    const [p] = [...pointers.values()];

    startPointerX = p.x;
    startPointerY = p.y;

    startX = x;
    startY = y;
  }

  if (pointers.size === 0) {
    pinchStartDistance = 0;
  }
});

window.addEventListener("mousemove", (e) => {
  lastMouseX = e.clientX;
  lastMouseY = e.clientY;

  if (testPinch) {
    pointers.set(virtualPointerId, {
      x: e.clientX,
      y: e.clientY,
    });
  }
});

window.addEventListener("keydown", (e) => {
  if (e.key !== "Shift" || testPinch) return;

  testPinch = true;

  // Virtual second finger
  const virtualX = lastMouseX + 100;
  const virtualY = lastMouseY;

  pointers.set(virtualPointerId, {
    x: virtualX,
    y: virtualY,
  });

  // If the real mouse pointer is already in the map,
  // start the pinch.
  if (pointers.size === 2) {
    const [p1, p2] = [...pointers.values()];

    pinchStartDistance = Math.hypot(p2.x - p1.x, p2.y - p1.y);

    pinchStartZoom = zoom;
  }

  console.log("Virtual finger started");
});

window.addEventListener("keyup", (e) => {

  if (e.key !== "Shift")
    return;

  testPinch = false;

  pointers.delete(virtualPointerId);

  pinchStartDistance = 0;

  console.log("Virtual finger removed");
});
//#endregion
