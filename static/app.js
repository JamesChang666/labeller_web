const state = {
  root: "",
  mode: "images",
  split: "train",
  images: [],
  idx: 0,
  img: null,
  rects: [],
  prevRects: [],
  sel: -1,
  scale: 1,
  ox: 0,
  oy: 0,
  dragging: false,
  dragMode: "draw", // draw | move
  start: null,
  moveBase: null,
  undo: [],
  redo: [],
};

const $ = (id) => document.getElementById(id);
const canvas = $("canvas");
const ctx = canvas.getContext("2d");

function setStatus(msg) {
  $("status").textContent = msg;
  $("statusTop").textContent = `${state.idx + 1}/${state.images.length}`;
}

async function api(path, method = "GET", body = null) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function browseFolder(title = "Select Folder") {
  const data = await api(`/api/dialog/folder?title=${encodeURIComponent(title)}`);
  return data.path || "";
}

async function browseFile(title = "Select File", kind = "all") {
  const data = await api(
    `/api/dialog/file?title=${encodeURIComponent(title)}&kind=${encodeURIComponent(kind)}`
  );
  return data.path || "";
}

function pushUndo() {
  state.undo.push(structuredClone(state.rects));
  if (state.undo.length > 100) state.undo.shift();
  state.redo = [];
}

function doUndo() {
  if (!state.undo.length) return;
  state.redo.push(structuredClone(state.rects));
  state.rects = state.undo.pop();
  state.sel = -1;
  draw();
}

function doRedo() {
  if (!state.redo.length) return;
  state.undo.push(structuredClone(state.rects));
  state.rects = state.redo.pop();
  state.sel = -1;
  draw();
}

async function refreshModels() {
  const data = await api("/api/models");
  const sel = $("modelSel");
  const cur = sel.value;
  sel.innerHTML = "";
  for (const m of data.models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    sel.appendChild(opt);
  }
  if (cur) sel.value = cur;
}

async function refreshRestoreList() {
  if (!state.root) return;
  const data = await api(`/api/restore/list?split=${encodeURIComponent(state.split)}`);
  const sel = $("restoreSel");
  sel.innerHTML = "";
  const files = data.files || [];
  if (!files.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No removed images";
    sel.appendChild(opt);
    return;
  }
  for (const f of files) {
    const opt = document.createElement("option");
    opt.value = f;
    opt.textContent = f;
    sel.appendChild(opt);
  }
}

function refreshImageDropdown() {
  const sel = $("imageSel");
  sel.innerHTML = "";
  state.images.forEach((p, i) => {
    const opt = document.createElement("option");
    opt.value = String(i);
    opt.textContent = p.split(/[\\/]/).pop();
    sel.appendChild(opt);
  });
  sel.value = String(state.idx);
}

async function loadClasses() {
  const data = await api("/api/classes");
  $("classNames").value = data.class_names.join(",");
}

async function saveClasses() {
  const names = $("classNames").value.split(",").map((s) => s.trim()).filter(Boolean);
  if (!names.length) return setStatus("Class names cannot be empty");
  await api("/api/classes", "POST", { names });
  setStatus("Class names updated");
}

async function openProject() {
  const path = $("projectPath").value.trim();
  if (!path) return setStatus("Enter project path first");
  state.mode = $("sourceMode").value;
  const data = await api("/api/project/open", "POST", { path, mode: state.mode });
  state.root = data.root;
  state.split = data.split;
  state.images = data.images;
  state.idx = 0;
  state.undo = [];
  state.redo = [];
  $("splitSel").value = state.split;
  refreshImageDropdown();
  await loadClasses();
  await refreshRestoreList();
  if (!state.images.length) return setStatus("No images found");
  await loadCurrent();
}

async function changeSplit() {
  if (!state.root) return;
  await saveCurrent();
  const split = $("splitSel").value;
  const data = await api("/api/project/split", "POST", { split });
  state.split = data.split;
  state.images = data.images;
  state.idx = 0;
  state.undo = [];
  state.redo = [];
  refreshImageDropdown();
  await refreshRestoreList();
  await loadCurrent();
}

function fit() {
  if (!state.img) return;
  const w = canvas.width;
  const h = canvas.height;
  state.scale = Math.min(w / state.img.width, h / state.img.height);
  state.ox = (w - state.img.width * state.scale) / 2;
  state.oy = (h - state.img.height * state.scale) / 2;
}

function imgToCanvas(x, y) {
  return [x * state.scale + state.ox, y * state.scale + state.oy];
}

function canvasToImg(x, y) {
  return [(x - state.ox) / state.scale, (y - state.oy) / state.scale];
}

function drawHandles(r) {
  const pts = [
    [r[0], r[1]], [(r[0]+r[2])/2, r[1]], [r[2], r[1]],
    [r[2], (r[1]+r[3])/2], [r[2], r[3]], [(r[0]+r[2])/2, r[3]],
    [r[0], r[3]], [r[0], (r[1]+r[3])/2],
  ];
  for (const p of pts) {
    const [x, y] = imgToCanvas(p[0], p[1]);
    ctx.fillStyle = "#00d4ff";
    ctx.fillRect(x - 3, y - 3, 6, 6);
  }
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!state.img) return;
  fit();
  ctx.drawImage(state.img, state.ox, state.oy, state.img.width * state.scale, state.img.height * state.scale);
  state.rects.forEach((r, i) => {
    const [x1, y1] = imgToCanvas(r[0], r[1]);
    const [x2, y2] = imgToCanvas(r[2], r[3]);
    ctx.strokeStyle = i === state.sel ? "#00d4ff" : "#ff3b30";
    ctx.lineWidth = i === state.sel ? 3 : 2;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillRect(x1, y1 - 16, 64, 16);
    ctx.fillStyle = "#fff";
    ctx.font = "12px Segoe UI";
    ctx.fillText(`C${r[4]}`, x1 + 4, y1 - 4);
    if (i === state.sel) drawHandles(r);
  });
}

async function loadCurrent() {
  if (!state.images.length) {
    state.img = null;
    state.rects = [];
    draw();
    setStatus("No images in current split");
    return;
  }
  const p = state.images[state.idx];
  $("imageSel").value = String(state.idx);

  const img = new Image();
  img.src = `/api/image?path=${encodeURIComponent(p)}`;
  await img.decode();
  state.img = img;

  const data = await api(`/api/labels?image_path=${encodeURIComponent(p)}&split=${encodeURIComponent(state.split)}`);
  const loaded = data.rects || [];
  const hasLabelFile = !!data.has_label_file;

  let rects = loaded;
  if (!hasLabelFile && $("chkPropagate").checked && state.prevRects.length) {
    rects = structuredClone(state.prevRects);
  }

  state.rects = rects;
  state.sel = -1;
  state.undo = [];
  state.redo = [];
  draw();

  if (!hasLabelFile && $("chkAutoDetect").checked) {
    await detect(true);
  }

  state.prevRects = structuredClone(state.rects);
  setStatus(`${p}`);
}

async function saveCurrent() {
  if (!state.images.length) return;
  const p = state.images[state.idx];
  await api("/api/labels/save", "POST", {
    image_path: p,
    split: state.split,
    rects: state.rects,
  });
}

function clampRect(r) {
  const w = state.img.width;
  const h = state.img.height;
  const x1 = Math.max(0, Math.min(w, Math.min(r[0], r[2])));
  const y1 = Math.max(0, Math.min(h, Math.min(r[1], r[3])));
  const x2 = Math.max(0, Math.min(w, Math.max(r[0], r[2])));
  const y2 = Math.max(0, Math.min(h, Math.max(r[1], r[3])));
  return [x1, y1, x2, y2, r[4]];
}

function next() {
  saveCurrent().then(async () => {
    if (state.idx < state.images.length - 1) state.idx++;
    await loadCurrent();
  });
}

function prev() {
  saveCurrent().then(async () => {
    if (state.idx > 0) state.idx--;
    await loadCurrent();
  });
}

function propagateNow() {
  pushUndo();
  state.rects = structuredClone(state.prevRects || []);
  draw();
}

async function detect(silent = false) {
  if (!state.images.length) return;
  const model = $("modelSel").value || "yolo26m.pt";
  const conf = Number($("conf").value || 0.5);
  const cls = Number($("classId").value || 0);
  const p = state.images[state.idx];
  const data = await api("/api/detect", "POST", { image_path: p, model_path: model, conf, cls });
  pushUndo();
  state.rects = state.rects.concat(data.rects || []);
  draw();
  if (!silent) setStatus(`Detected ${(data.rects || []).length} boxes by ${data.model || model}`);
}

function removeSelected() {
  if (state.sel >= 0) {
    pushUndo();
    state.rects.splice(state.sel, 1);
    state.sel = -1;
    draw();
  }
}

function clearAll() {
  if (!state.rects.length) return;
  pushUndo();
  state.rects = [];
  state.sel = -1;
  draw();
}

async function removeCurrentImage() {
  if (!state.images.length) return;
  await saveCurrent();
  const p = state.images[state.idx];
  const data = await api("/api/remove", "POST", { image_path: p, split: state.split });
  state.images = data.images;
  if (state.idx >= state.images.length) state.idx = Math.max(0, state.images.length - 1);
  refreshImageDropdown();
  await refreshRestoreList();
  await loadCurrent();
  setStatus(`Removed: ${data.removed}`);
}

async function restoreImage() {
  const filename = $("restoreSel").value || "";
  if (!filename) return setStatus("Select a removed filename first");
  const data = await api("/api/restore", "POST", { split: state.split, filename });
  state.images = data.images;
  refreshImageDropdown();
  await refreshRestoreList();
  await loadCurrent();
  setStatus(`Restored: ${data.restored}`);
}

function fuseBoxes() {
  if (state.rects.length <= 1) return;
  pushUndo();
  const used = new Array(state.rects.length).fill(false);
  const out = [];
  const iou = (a, b) => {
    const x1 = Math.max(a[0], b[0]);
    const y1 = Math.max(a[1], b[1]);
    const x2 = Math.min(a[2], b[2]);
    const y2 = Math.min(a[3], b[3]);
    if (x2 <= x1 || y2 <= y1) return 0;
    const inter = (x2 - x1) * (y2 - y1);
    const ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter;
    return ua > 0 ? inter / ua : 0;
  };
  for (let i = 0; i < state.rects.length; i++) {
    if (used[i]) continue;
    let c = [...state.rects[i]];
    used[i] = true;
    for (let j = i + 1; j < state.rects.length; j++) {
      if (used[j]) continue;
      if (c[4] !== state.rects[j][4]) continue;
      if (iou(c, state.rects[j]) > 0.3) {
        c = [Math.min(c[0], state.rects[j][0]), Math.min(c[1], state.rects[j][1]), Math.max(c[2], state.rects[j][2]), Math.max(c[3], state.rects[j][3]), c[4]];
        used[j] = true;
      }
    }
    out.push(c);
  }
  state.rects = out;
  draw();
}

async function exportAll() {
  const output_dir = $("exportPath").value.trim();
  const fmt = $("exportFmt").value;
  if (!output_dir) return setStatus("Enter export path");
  await saveCurrent();
  const data = await api("/api/export", "POST", { output_dir, fmt });
  setStatus(`Exported ${data.count} images to ${data.output}`);
}

async function importModel() {
  const path = $("modelPath").value.trim();
  if (!path) return;
  const data = await api("/api/models/import", "POST", { path });
  await refreshModels();
  $("modelSel").value = data.selected;
}

canvas.addEventListener("mousedown", (e) => {
  if (!state.img) return;
  const rect = canvas.getBoundingClientRect();
  const [ix, iy] = canvasToImg(e.clientX - rect.left, e.clientY - rect.top);

  state.sel = -1;
  for (let i = state.rects.length - 1; i >= 0; i--) {
    const r = state.rects[i];
    if (ix >= Math.min(r[0], r[2]) && ix <= Math.max(r[0], r[2]) && iy >= Math.min(r[1], r[3]) && iy <= Math.max(r[1], r[3])) {
      state.sel = i;
      $("classId").value = String(state.rects[i][4]);
      pushUndo();
      state.dragging = true;
      state.dragMode = "move";
      state.start = [ix, iy];
      state.moveBase = [...r];
      draw();
      return;
    }
  }

  state.dragging = true;
  state.dragMode = "draw";
  state.start = [ix, iy];
});

canvas.addEventListener("mousemove", (e) => {
  if (!state.img || !state.dragging || !state.start) return;
  const rect = canvas.getBoundingClientRect();
  const [ix, iy] = canvasToImg(e.clientX - rect.left, e.clientY - rect.top);

  if (state.dragMode === "move" && state.sel >= 0 && state.moveBase) {
    const dx = ix - state.start[0];
    const dy = iy - state.start[1];
    const r = [
      state.moveBase[0] + dx,
      state.moveBase[1] + dy,
      state.moveBase[2] + dx,
      state.moveBase[3] + dy,
      state.moveBase[4],
    ];
    state.rects[state.sel] = clampRect(r);
    draw();
  }
});

canvas.addEventListener("mouseup", (e) => {
  if (!state.img || !state.dragging) return;
  const rect = canvas.getBoundingClientRect();
  const [ix, iy] = canvasToImg(e.clientX - rect.left, e.clientY - rect.top);

  if (state.dragMode === "draw") {
    const cid = Number($("classId").value || 0);
    const r = clampRect([state.start[0], state.start[1], ix, iy, cid]);
    if (Math.abs(r[2] - r[0]) > 2 && Math.abs(r[3] - r[1]) > 2) {
      pushUndo();
      state.rects.push(r);
      state.sel = state.rects.length - 1;
    }
  } else if (state.dragMode === "move") {
    // undo snapshot captured on mousedown
  }

  state.dragging = false;
  state.start = null;
  state.moveBase = null;
  draw();
});

$("classId").addEventListener("change", () => {
  if (state.sel >= 0) {
    pushUndo();
    state.rects[state.sel][4] = Number($("classId").value || 0);
    draw();
  }
});

window.addEventListener("keydown", (e) => {
  if (e.key === "f" || e.key === "F") next();
  if (e.key === "d" || e.key === "D") prev();
  if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) {
    e.preventDefault();
    doUndo();
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === "y" || e.key === "Y")) {
    e.preventDefault();
    doRedo();
  }
  if (e.key === "Delete") removeSelected();
  if (e.key === "a" || e.key === "A") detect().catch((err) => setStatus(err.message));
});
window.addEventListener("beforeunload", () => {
  saveCurrent().catch(() => {});
});

$("imageSel").onchange = async () => {
  await saveCurrent();
  state.idx = Number($("imageSel").value || 0);
  await loadCurrent();
};

$("btnOpen").onclick = () => openProject().catch((e) => setStatus(e.message));
$("btnBrowseProject").onclick = async () => {
  try {
    const p = await browseFolder("Select Dataset Folder");
    if (p) $("projectPath").value = p;
  } catch (e) {
    setStatus(e.message);
  }
};
$("splitSel").onchange = () => changeSplit().catch((e) => setStatus(e.message));
$("btnNext").onclick = () => next();
$("btnPrev").onclick = () => prev();
$("btnPropagate").onclick = propagateNow;
$("btnDetect").onclick = () => detect().catch((e) => setStatus(e.message));
$("btnDelete").onclick = removeSelected;
$("btnClearAll").onclick = clearAll;
$("btnUndo").onclick = doUndo;
$("btnRedo").onclick = doRedo;
$("btnFuse").onclick = fuseBoxes;
$("btnRemove").onclick = () => removeCurrentImage().catch((e) => setStatus(e.message));
$("btnRestore").onclick = () => restoreImage().catch((e) => setStatus(e.message));
$("btnExport").onclick = () => exportAll().catch((e) => setStatus(e.message));
$("btnImportModel").onclick = () => importModel().catch((e) => setStatus(e.message));
$("btnBrowseModel").onclick = async () => {
  try {
    const p = await browseFile("Select Model File", "model");
    if (p) $("modelPath").value = p;
  } catch (e) {
    setStatus(e.message);
  }
};
$("btnBrowseExport").onclick = async () => {
  try {
    const p = await browseFolder("Select Export Folder");
    if (p) $("exportPath").value = p;
  } catch (e) {
    setStatus(e.message);
  }
};
$("btnSaveClasses").onclick = () => saveClasses().catch((e) => setStatus(e.message));

refreshModels().catch((e) => setStatus(e.message));
loadClasses().catch((e) => setStatus(e.message));
setStatus("Ready");
