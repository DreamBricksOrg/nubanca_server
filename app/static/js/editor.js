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

const coverImage = new Image();
const photoTaken = new Image();

let photoTakenHeight = 0;
let zoom = 1;
let displayScale = 1;
let moveInterval = null;
let testPinch = false;
let virtualPointerId = "virtual";
let lastMouseX = 0;
let lastMouseY = 0;

coverImage.src = coverImagePath;
const photoTakenPath = localStorage.getItem("imgData");
photoTaken.src = photoTakenPath;

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

  const scaleX = horizontalSpace / coverImage.width;
  const scaleY = verticalSpace / coverImage.height;

  return Math.min(scaleX, scaleY);
}

// IMAGE 1
coverImage.onload = () => {
  displayScale = getDisplayScale();
  canvas1.width = coverImage.width * displayScale;
  canvas1.height = coverImage.height * displayScale;

  ctx1.drawImage(coverImage, 0, 0, canvas1.width, canvas1.height);
  setupEditor();
};

// IMAGE 2
photoTaken.onload = () => {
  displayScale = getDisplayScale();

  canvas2.width = coverImage.width * displayScale;
  canvas2.height = coverImage.height * displayScale;

  const scale = canvas2.width / photoTaken.width;

  photoTakenHeight = photoTaken.height * scale;

  x = canvas2.width / 2;
  y = canvas2.height / 2;

  drawPhotoTaken();
  setupEditor();
};

function drawPhotoTaken() {
  ctx2.clearRect(0, 0, canvas2.width, canvas2.height);

  const width = canvas2.width * zoom;
  const height = photoTakenHeight * zoom;

  ctx2.save();

  ctx2.translate(x, y);

  ctx2.drawImage(photoTaken, -width / 2, -height / 2, width, height);

  ctx2.restore();
}

function setupEditor() {
  if (!coverImage.complete || !photoTaken.complete) return;

  const editor = document.getElementById("editor");

  editor.style.width = canvas1.width + "px";
  editor.style.height = canvas1.height + "px";
}

function startMoving(dx, dy) {
  if (moveInterval) return;

  movePhotoTaken(dx, dy);

  moveInterval = setInterval(() => {
    movePhotoTaken(dx, dy);
  }, 100);
}

function stopMoving() {
  clearInterval(moveInterval);
  moveInterval = null;
}

function movePhotoTaken(dx, dy) {
  x += dx;
  y += dy;

  drawPhotoTaken();
}

function saveImage() {
  const outputCanvas = document.createElement("canvas");

  outputCanvas.width = coverImage.width;
  outputCanvas.height = coverImage.height;

  const ctx = outputCanvas.getContext("2d");

  // Draw Image 2
  const originalX = x / displayScale;
  const originalY = y / displayScale;

  const originalWidth = (canvas2.width * zoom) / displayScale;
  const originalHeight = (photoTakenHeight * zoom) / displayScale;

  ctx.save();

  ctx.translate(originalX, originalY);

  ctx.drawImage(
    photoTaken,
    -originalWidth / 2,
    -originalHeight / 2,
    originalWidth,
    originalHeight,
  );

  ctx.restore();

  // Draw Image 1 on top
  ctx.drawImage(coverImage, 0, 0, coverImage.width, coverImage.height);

  outputCanvas.toBlob(async (blob) => {
    const formData = new FormData();

    formData.append("image", blob, "edited-image.png");

    let resp = await fetch(BASE_URL + "/print", {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      throw new Error("Erro na requisição: " + resp.status);
    }

    const dados = await resp.json();

    localStorage.setItem("qrcodeImagePath", dados.page_url);
    window.location.href = BASE_URL + "/qrcode";
  }, "image/png");
}

//#region screen display
window.addEventListener("resize", () => {
  if (!coverImage.complete || !photoTaken.complete) return;

  displayScale = getDisplayScale();

  canvas1.width = coverImage.width * displayScale;
  canvas1.height = coverImage.height * displayScale;

  ctx1.drawImage(coverImage, 0, 0, canvas1.width, canvas1.height);

  canvas2.width = canvas1.width;
  canvas2.height = canvas1.height;

  const scale = canvas2.width / photoTaken.width;

  photoTakenHeight = photoTaken.height * scale;

  drawPhotoTaken();
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
  drawPhotoTaken();
});

window.addEventListener("mouseup", stopMoving);

input_zoom_out.addEventListener("click", () => {
  zoom = Math.max(0.1, zoom - 0.1);
  drawPhotoTaken();
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

    drawPhotoTaken();
    return;
  }
  if (pointers.size === 2) {
    const [p1, p2] = [...pointers.values()];

    const currentDistance = Math.hypot(p2.x - p1.x, p2.y - p1.y);

    if (pinchStartDistance === 0) return;

    const ratio = currentDistance / pinchStartDistance;

    zoom = Math.max(0.1, pinchStartZoom * ratio);

    drawPhotoTaken();
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
  if (e.key !== "Shift") return;

  testPinch = false;

  pointers.delete(virtualPointerId);

  pinchStartDistance = 0;

  console.log("Virtual finger removed");
});
//#endregion
