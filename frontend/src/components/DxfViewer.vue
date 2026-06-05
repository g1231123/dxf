<script setup>
import { onMounted, onBeforeUnmount, ref, defineExpose, defineEmits } from "vue";
import * as THREE from "three";
import { DXFViewer } from "three-dxf-viewer";
import DxfParser from "dxf-parser";

const mount = ref(null);                 // outer wrapper
const overlayRoot = ref(null);           // HTML text overlay container
const emit = defineEmits(["measure", "selection", "edits"]);

// ---------------------------------------------------------------------------
// Three.js handles
// ---------------------------------------------------------------------------
let renderer, scene, camera, parserViewer;
let dxfRoot = null;
let bbox = new THREE.Box3();
let animId = null;
let currentFile = null;                 // stash original File for export

// ---------------------------------------------------------------------------
// Interaction state
// ---------------------------------------------------------------------------
const ctrl = {
  panning: false,
  draggingSelection: false,
  lastX: 0,
  lastY: 0,
  worldStart: null,
};

const measure = {
  enabled: false,
  first: null,
  markerGroup: null,
};

// Layer name -> Object3D[]
const layersIndex = new Map();

// Selection: array of { obj, originalColor, entity }
const selection = [];

// Edit journal — applied to DXF on export via the backend (ezdxf).
// Each entry: { op: "move", handle, dx, dy } or { op: "delete", handle }
//             or { op: "text", handle, value }
const editJournal = [];

// Text overlay: array of { entity, el, x, y, h, layer, visible }
const textItems = [];

// Parsed DXF entities from dxf-parser (for text overlay)
let parsedEntities = [];

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
function init() {
  const el = mount.value;
  const { clientWidth: w, clientHeight: h } = el;

  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: false,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(w, h);
  renderer.setClearColor(0xfafafa, 1); // AutoCAD-ish light background
  el.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xfafafa);

  camera = new THREE.OrthographicCamera(-w / 2, w / 2, h / 2, -h / 2, -10000, 10000);
  camera.position.set(0, 0, 100);
  camera.lookAt(0, 0, 0);

  parserViewer = new DXFViewer();

  bindEvents();
  animate();
}

function animate() {
  animId = requestAnimationFrame(animate);
  renderer.render(scene, camera);
  syncTextOverlay();
}

function onResize() {
  if (!mount.value) return;
  const { clientWidth: w, clientHeight: h } = mount.value;
  renderer.setSize(w, h);
  if (dxfRoot) {
    fitExtent();
  } else {
    camera.left = -w / 2;
    camera.right = w / 2;
    camera.top = h / 2;
    camera.bottom = -h / 2;
    camera.updateProjectionMatrix();
  }
}

function bindEvents() {
  const el = renderer.domElement;
  el.addEventListener("mousedown", onMouseDown);
  el.addEventListener("mousemove", onMouseMove);
  el.addEventListener("mouseup", onMouseUp);
  el.addEventListener("mouseleave", onMouseUp);
  el.addEventListener("wheel", onWheel, { passive: false });
  el.addEventListener("dblclick", onDoubleClick);
  el.addEventListener("contextmenu", (e) => e.preventDefault());
  window.addEventListener("resize", onResize);
  window.addEventListener("keydown", onKeyDown);
}

function unbindEvents() {
  const el = renderer?.domElement;
  if (el) {
    el.removeEventListener("mousedown", onMouseDown);
    el.removeEventListener("mousemove", onMouseMove);
    el.removeEventListener("mouseup", onMouseUp);
    el.removeEventListener("mouseleave", onMouseUp);
    el.removeEventListener("wheel", onWheel);
    el.removeEventListener("dblclick", onDoubleClick);
  }
  window.removeEventListener("resize", onResize);
  window.removeEventListener("keydown", onKeyDown);
}

// ---------------------------------------------------------------------------
// Mouse / keyboard
// ---------------------------------------------------------------------------
function onMouseDown(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const world = screenToWorld(mx, my);

  if (measure.enabled && e.button === 0) {
    handleMeasureClick(world);
    return;
  }

  if (e.button === 0) {
    // Left click: select / start drag
    const hit = pickEntity(mx, my);
    if (hit) {
      // If clicked entity is part of current selection -> start dragging it
      const inSelection = selection.some((s) => s.obj === hit.obj);
      if (!inSelection) {
        if (!e.shiftKey) clearSelection();
        addToSelection(hit);
      }
      ctrl.draggingSelection = true;
      ctrl.worldStart = world;
      ctrl.lastX = e.clientX;
      ctrl.lastY = e.clientY;
      renderer.domElement.style.cursor = "move";
      return;
    } else {
      if (!e.shiftKey) clearSelection();
    }
  }

  // Pan with right-click or middle-click, or left-click on empty space.
  ctrl.panning = true;
  ctrl.lastX = e.clientX;
  ctrl.lastY = e.clientY;
  renderer.domElement.style.cursor = "grabbing";
}

function onMouseMove(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  if (ctrl.draggingSelection) {
    const world = screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
    const dx = world.x - ctrl.worldStart.x;
    const dy = world.y - ctrl.worldStart.y;
    for (const sel of selection) {
      sel.obj.position.x = (sel._origX ?? 0) + dx;
      sel.obj.position.y = (sel._origY ?? 0) + dy;
    }
    return;
  }
  if (ctrl.panning) {
    const dx = e.clientX - ctrl.lastX;
    const dy = e.clientY - ctrl.lastY;
    ctrl.lastX = e.clientX;
    ctrl.lastY = e.clientY;
    const sx = (camera.right - camera.left) / renderer.domElement.clientWidth;
    const sy = (camera.top - camera.bottom) / renderer.domElement.clientHeight;
    camera.position.x -= dx * sx;
    camera.position.y += dy * sy;
  }
}

function onMouseUp(e) {
  if (ctrl.draggingSelection) {
    // Commit translation -> bake into world matrix and write edit op
    const world = screenToWorld(
      e.clientX - renderer.domElement.getBoundingClientRect().left,
      e.clientY - renderer.domElement.getBoundingClientRect().top
    );
    const dx = world.x - ctrl.worldStart.x;
    const dy = world.y - ctrl.worldStart.y;
    if (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6) {
      for (const sel of selection) {
        const handle = sel.entity?.handle;
        if (!handle) continue;
        editJournal.push({ op: "move", handle, dx, dy });
        // Move the associated overlay text item too
        const t = textItems.find((t) => normHandle(t.entity?.handle) === normHandle(handle));
        if (t) {
          t.x += dx;
          t.y += dy;
        }
      }
      // Refresh origins so subsequent drags accumulate correctly
      for (const sel of selection) {
        sel._origX = sel.obj.position.x;
        sel._origY = sel.obj.position.y;
      }
      emit("edits", editJournal.slice());
    }
    ctrl.draggingSelection = false;
  }
  ctrl.panning = false;
  renderer.domElement.style.cursor = measure.enabled ? "crosshair" : "default";
}

function onWheel(e) {
  e.preventDefault();
  const rect = renderer.domElement.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const before = screenToWorld(mx, my);
  const factor = e.deltaY > 0 ? 1.12 : 1 / 1.12;
  zoomBy(1 / factor);
  const after = screenToWorld(mx, my);
  camera.position.x += before.x - after.x;
  camera.position.y += before.y - after.y;
}

function onDoubleClick(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  // Try to hit a TEXT overlay first (HTML overlay handles those clicks itself);
  // here we just check geometry hits (e.g. could open property dialog later).
  const hit = pickEntity(mx, my);
  if (hit && (hit.entity?.type === "TEXT" || hit.entity?.type === "MTEXT")) {
    promptEditText(hit.entity);
  }
}

function onKeyDown(e) {
  // Only respond when our viewport has focus-ish (not inside an <input>)
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  if ((e.key === "Delete" || e.key === "Backspace") && selection.length) {
    deleteSelection();
    e.preventDefault();
  } else if (e.key === "Escape") {
    clearSelection();
    if (measure.enabled) {
      measure.first = null;
      if (measure.markerGroup) scene.remove(measure.markerGroup);
      measure.markerGroup = null;
    }
  }
}

// ---------------------------------------------------------------------------
// Coordinate helpers
// ---------------------------------------------------------------------------
function screenToWorld(mx, my) {
  const w = renderer.domElement.clientWidth;
  const h = renderer.domElement.clientHeight;
  const nx = (mx / w) * 2 - 1;
  const ny = -(my / h) * 2 + 1;
  return new THREE.Vector3(nx, ny, 0).unproject(camera);
}

function worldToScreen(x, y) {
  const v = new THREE.Vector3(x, y, 0).project(camera);
  const w = renderer.domElement.clientWidth;
  const h = renderer.domElement.clientHeight;
  return {
    x: ((v.x + 1) * w) / 2,
    y: ((1 - v.y) * h) / 2,
    behind: v.z > 1 || v.z < -1,
  };
}

function zoomBy(factor) {
  const cx = (camera.left + camera.right) / 2;
  const cy = (camera.top + camera.bottom) / 2;
  const halfW = ((camera.right - camera.left) * factor) / 2;
  const halfH = ((camera.top - camera.bottom) * factor) / 2;
  camera.left = cx - halfW;
  camera.right = cx + halfW;
  camera.top = cy + halfH;
  camera.bottom = cy - halfH;
  camera.updateProjectionMatrix();
}

function fitExtent() {
  if (!dxfRoot || !mount.value) return;
  bbox.setFromObject(dxfRoot);
  if (!isFinite(bbox.min.x) || bbox.isEmpty()) return;
  const { clientWidth: w, clientHeight: h } = mount.value;
  const dxW = bbox.max.x - bbox.min.x || 1;
  const dyH = bbox.max.y - bbox.min.y || 1;
  const aspect = w / h;
  const dxfAspect = dxW / dyH;
  let halfW, halfH;
  if (dxfAspect > aspect) {
    halfW = dxW / 2;
    halfH = halfW / aspect;
  } else {
    halfH = dyH / 2;
    halfW = halfH * aspect;
  }
  halfW *= 1.05;
  halfH *= 1.05;
  const cx = (bbox.min.x + bbox.max.x) / 2;
  const cy = (bbox.min.y + bbox.max.y) / 2;
  camera.left = -halfW;
  camera.right = halfW;
  camera.top = halfH;
  camera.bottom = -halfH;
  camera.position.set(cx, cy, 100);
  camera.updateProjectionMatrix();
}

// ---------------------------------------------------------------------------
// Picking — raycast in screen space using small tolerance
// ---------------------------------------------------------------------------
const ray = new THREE.Raycaster();
ray.params.Line.threshold = 1; // updated per-load to scene scale
ray.params.Points.threshold = 1;

function pickEntity(mx, my) {
  if (!dxfRoot) return null;
  const w = renderer.domElement.clientWidth;
  const h = renderer.domElement.clientHeight;
  const ndc = new THREE.Vector2((mx / w) * 2 - 1, -(my / h) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  // Tolerance scales with current view size so picking feels uniform at any zoom
  const worldPerPx = (camera.right - camera.left) / w;
  ray.params.Line.threshold = worldPerPx * 6;
  ray.params.Points.threshold = worldPerPx * 8;
  const hits = ray.intersectObject(dxfRoot, true);
  for (const h of hits) {
    const obj = h.object;
    if (!obj.visible) continue;
    const entity = entityOf(obj);
    if (entity) return { obj, entity, distance: h.distance };
  }
  return null;
}

function entityOf(obj) {
  let cur = obj;
  while (cur) {
    if (cur.userData?.entity) return cur.userData.entity;
    cur = cur.parent;
  }
  return null;
}

// Normalize handle to string for consistent matching between dxf-parser and three-dxf-viewer
function normHandle(h) {
  if (h === null || h === undefined) return null;
  const s = String(h).toUpperCase();
  // Remove leading zeros but keep at least one digit
  return s.replace(/^0+(?=.)/, "") || "0";
}

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------
function addToSelection(hit) {
  // Don't double-add
  if (selection.some((s) => s.obj === hit.obj)) return;
  // Highlight: switch material color to red (clone material first)
  const obj = hit.obj;
  let originalColor = null;
  try {
    if (obj.material && obj.material.color) {
      // Clone material so other objects sharing it stay unchanged
      obj.material = obj.material.clone();
      originalColor = obj.material.color.getHex();
      obj.material.color.set(0xff3344);
    }
  } catch (_) {}
  selection.push({
    obj,
    originalColor,
    entity: hit.entity,
    _origX: obj.position.x,
    _origY: obj.position.y,
  });
  emitSelection();
}

function clearSelection() {
  for (const s of selection) {
    if (s.originalColor !== null && s.obj.material?.color) {
      s.obj.material.color.setHex(s.originalColor);
    }
  }
  selection.length = 0;
  emitSelection();
}

function deleteSelection() {
  for (const s of selection) {
    s.obj.visible = false;
    if (s.entity?.handle) {
      editJournal.push({ op: "delete", handle: s.entity.handle });
      // Also hide the matching text overlay
      const t = textItems.find((t) => normHandle(t.entity?.handle) === normHandle(s.entity.handle));
      if (t) t.visible = false;
    }
  }
  selection.length = 0;
  emitSelection();
  emit("edits", editJournal.slice());
}

function emitSelection() {
  emit("selection", selection.map((s) => ({
    handle: s.entity?.handle,
    type: s.entity?.type,
    layer: s.entity?.layer,
  })));
}

// ---------------------------------------------------------------------------
// HTML text overlay  (the proper fix for CJK)
// ---------------------------------------------------------------------------
function rebuildTextOverlay() {
  // Wipe previous overlay entries
  if (overlayRoot.value) overlayRoot.value.innerHTML = "";
  textItems.length = 0;

  // Use entities parsed by dxf-parser (not three-dxf-viewer)
  if (!parsedEntities?.length) return;

  for (const entity of parsedEntities) {
    if (entity.type !== "TEXT" && entity.type !== "MTEXT") continue;
    // dxf-parser uses: text (TEXT), contents (MTEXT), or string fallback
    const value = entity.text ?? entity.contents ?? entity.string ?? "";
    if (!value) continue;
    // Position variants across DXF versions
    const pos = entity.position || entity.insertionPoint || entity.startPoint || { x: 0, y: 0 };
    const height = entity.textHeight || entity.height || entity.nominalHeight || 1;
    const item = {
      entity,
      x: pos.x ?? 0,
      y: pos.y ?? 0,
      h: height,
      visible: true,
      el: document.createElement("div"),
    };
    item.el.className = "dxf-text";
    item.el.style.color = "#1a3050";
    item.el.style.position = "absolute";
    item.el.style.transformOrigin = "left bottom";
    item.el.style.whiteSpace = "pre";
    item.el.style.pointerEvents = "auto";
    item.el.style.cursor = "text";
    item.el.textContent = value.replace(/\\P/g, "\n").replace(/\\[A-Za-z][^;]*;/g, "");
    item.el.title = `[${entity.layer || "0"}] ${entity.type}`;
    item.el.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      promptEditText(entity, item);
    });
    overlayRoot.value.appendChild(item.el);
    textItems.push(item);
  }

  // Hide three.js text meshes since we now render text via HTML
  if (dxfRoot) {
    dxfRoot.traverse((o) => {
      const ent = o.userData?.entity;
      if (ent && (ent.type === "TEXT" || ent.type === "MTEXT")) {
        o.visible = false;
      }
    });
  }
}

function syncTextOverlay() {
  if (!overlayRoot.value || !textItems.length) return;
  const w = renderer.domElement.clientWidth;
  const h = renderer.domElement.clientHeight;
  const worldPerPx = (camera.right - camera.left) / w;
  for (const t of textItems) {
    if (!t.visible) {
      t.el.style.display = "none";
      continue;
    }
    const screen = worldToScreen(t.x, t.y);
    if (screen.x < -200 || screen.x > w + 200 || screen.y < -200 || screen.y > h + 200) {
      t.el.style.display = "none";
      continue;
    }
    // Convert DXF text height (in world units) to CSS px
    const fontPx = Math.max(8, t.h / worldPerPx);
    if (fontPx > 200) {
      // Too zoomed-in; cap to avoid layout explosion
      t.el.style.display = "none";
      continue;
    }
    t.el.style.display = "block";
    t.el.style.left = "0";
    t.el.style.top = "0";
    t.el.style.fontSize = `${fontPx}px`;
    // bottom-left of text sits on (x, y); CSS y grows downward so flip
    t.el.style.transform =
      `translate(${screen.x.toFixed(1)}px, ${screen.y.toFixed(1)}px) translateY(-100%)`;
  }
}

function promptEditText(entity, overlayItem = null) {
  const current = entity.text ?? entity.string ?? "";
  const next = window.prompt("修改文本", current);
  if (next === null || next === current) return;
  entity.text = next; // mutate in place so re-export sees it
  if (overlayItem) overlayItem.el.textContent = next;
  if (entity.handle) {
    editJournal.push({ op: "text", handle: entity.handle, value: next });
    emit("edits", editJournal.slice());
  }
}

// ---------------------------------------------------------------------------
// DXF loading
// ---------------------------------------------------------------------------
async function loadFile(file) {
  // Reset
  if (dxfRoot) {
    scene.remove(dxfRoot);
    disposeObject(dxfRoot);
    dxfRoot = null;
  }
  if (measure.markerGroup) {
    scene.remove(measure.markerGroup);
    measure.markerGroup = null;
  }
  selection.length = 0;
  editJournal.length = 0;
  emit("edits", []);
  if (overlayRoot.value) overlayRoot.value.innerHTML = "";
  textItems.length = 0;
  parsedEntities = [];

  currentFile = file;

  // Parse DXF separately with dxf-parser to get raw entities for text overlay
  const fileText = await file.text();
  try {
    const parser = new DxfParser();
    const dxfParsed = parser.parse(fileText);
    parsedEntities = dxfParsed?.entities || [];
  } catch (e) {
    console.warn("DXF parse for text overlay failed:", e);
  }

  const fontPath = "/fonts/helvetiker_regular.typeface.json";
  const dxf = await parserViewer.getFromFile(file, fontPath);
  if (!dxf || !dxf.isObject3D) {
    throw new Error("DXF 解析失败：未得到可渲染对象");
  }
  dxfRoot = dxf;
  scene.add(dxfRoot);

  // Index by layer + count entities
  const layerObjects = new Map();
  let entityCount = 0;
  dxfRoot.traverse((obj) => {
    if (!obj.isLine && !obj.isMesh && !obj.isLineSegments && !obj.isPoints) return;
    entityCount += 1;
    const ent = entityOf(obj);
    const name = ent?.layer || obj.userData?.layer || "0";
    if (!layerObjects.has(name)) layerObjects.set(name, []);
    layerObjects.get(name).push(obj);
  });

  layersIndex.clear();
  const layers = [];
  const parserLayers = parserViewer.layers || {};
  for (const name of Object.keys(parserLayers)) {
    const meta = parserLayers[name] || {};
    const objs = layerObjects.get(name) || [];
    layersIndex.set(name, objs);
    layers.push({ name, visible: true, color: colorToHex(meta.color, objs[0]) });
  }
  for (const [name, objs] of layerObjects.entries()) {
    if (parserLayers[name] !== undefined) continue;
    layersIndex.set(name, objs);
    layers.push({ name, visible: true, color: colorToHex(null, objs[0]) });
  }

  rebuildTextOverlay();
  fitExtent();

  return {
    entityCount,
    width: bbox.max.x - bbox.min.x,
    height: bbox.max.y - bbox.min.y,
    layers,
  };
}

function colorToHex(parserColor, sampleObject) {
  if (typeof parserColor === "number") {
    return "#" + parserColor.toString(16).padStart(6, "0");
  }
  if (parserColor && typeof parserColor === "object") {
    if ("color" in parserColor) return colorToHex(parserColor.color, sampleObject);
    if ("r" in parserColor) {
      const c = (Math.round(parserColor.r * 255) << 16) |
                (Math.round(parserColor.g * 255) << 8) |
                Math.round(parserColor.b * 255);
      return "#" + c.toString(16).padStart(6, "0");
    }
  }
  try {
    const c = sampleObject?.material?.color;
    if (c) return "#" + c.getHexString();
  } catch (_) {}
  return "#3a4a60";
}

function setLayerVisible(name, visible) {
  const objs = layersIndex.get(name);
  if (objs) for (const o of objs) o.visible = visible;
  // Also toggle text overlay items belonging to this layer
  for (const t of textItems) {
    if ((t.entity?.layer || "0") === name) {
      t.visible = visible;
      if (!visible) t.el.style.display = "none";
    }
  }
}

function zoomToExtent() {
  fitExtent();
}

function exportPng(baseName = "render") {
  // Render text overlay into the canvas via an off-screen approach: we just
  // composite the canvas + an html2canvas-like pass would be ideal, but for
  // simplicity we export the WebGL pixels alone. Text overlay is HTML and
  // intentionally not part of the WebGL canvas.
  renderer.render(scene, camera);
  const url = renderer.domElement.toDataURL("image/png");
  const a = document.createElement("a");
  a.href = url;
  a.download = `${baseName}.png`;
  a.click();
}

// ---------------------------------------------------------------------------
// Measure
// ---------------------------------------------------------------------------
function setMeasureEnabled(v) {
  measure.enabled = v;
  measure.first = null;
  renderer.domElement.style.cursor = v ? "crosshair" : "default";
  if (!v && measure.markerGroup) {
    scene.remove(measure.markerGroup);
    measure.markerGroup = null;
    emit("measure", { enabled: false, distance: null, angle: null });
  }
}

function handleMeasureClick(world) {
  if (!measure.first) {
    measure.first = { x: world.x, y: world.y };
    drawMeasureMarker([measure.first]);
    emit("measure", { enabled: true, distance: 0, angle: null });
  } else {
    const second = { x: world.x, y: world.y };
    const dx = second.x - measure.first.x;
    const dy = second.y - measure.first.y;
    const distance = Math.sqrt(dx * dx + dy * dy);
    const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
    drawMeasureMarker([measure.first, second]);
    emit("measure", { enabled: true, distance, angle });
    measure.first = null;
  }
}

function drawMeasureMarker(points) {
  if (measure.markerGroup) {
    scene.remove(measure.markerGroup);
    disposeObject(measure.markerGroup);
  }
  const g = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({ color: 0xff7700 });
  const dotMat = new THREE.PointsMaterial({ color: 0xff7700, size: 8, sizeAttenuation: false });
  if (points.length === 2) {
    const geom = new THREE.BufferGeometry().setFromPoints(
      points.map((p) => new THREE.Vector3(p.x, p.y, 1))
    );
    g.add(new THREE.Line(geom, mat));
  }
  const ptGeom = new THREE.BufferGeometry().setFromPoints(
    points.map((p) => new THREE.Vector3(p.x, p.y, 1))
  );
  g.add(new THREE.Points(ptGeom, dotMat));
  scene.add(g);
  measure.markerGroup = g;
}

function disposeObject(obj) {
  obj.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      const mats = Array.isArray(child.material) ? child.material : [child.material];
      mats.forEach((m) => m.dispose());
    }
  });
}

// ---------------------------------------------------------------------------
// Export with edits applied (DXF / DWG)
// ---------------------------------------------------------------------------
async function exportEdited(format = "dxf") {
  if (!currentFile) throw new Error("尚未加载文件");
  const fd = new FormData();
  fd.append("file", currentFile);
  fd.append("edits", JSON.stringify(editJournal));
  fd.append("format", format);
  const resp = await fetch("/api/edit/dxf", { method: "POST", body: fd });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`导出失败: ${resp.status} ${t}`);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stem = currentFile.name.replace(/\.(dxf|dwg)$/i, "");
  a.href = url;
  a.download = `${stem}.edited.${format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function clearEdits() {
  editJournal.length = 0;
  emit("edits", []);
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(() => {
  init();
  renderer.domElement.style.cursor = "default";
});

onBeforeUnmount(() => {
  if (animId) cancelAnimationFrame(animId);
  unbindEvents();
  if (dxfRoot) disposeObject(dxfRoot);
  renderer?.dispose();
});

defineExpose({
  loadFile,
  setLayerVisible,
  zoomToExtent,
  zoomBy,
  setMeasureEnabled,
  exportPng,
  exportEdited,
  clearEdits,
  deleteSelection,
});
</script>

<template>
  <div class="dxf-viewer" ref="mount">
    <!-- HTML overlay layer for crisp CJK text and editable labels -->
    <div class="text-overlay" ref="overlayRoot"></div>
  </div>
</template>

<style scoped>
.dxf-viewer {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(rgba(20, 27, 38, 0.06) 1px, transparent 1px) 0 0 / 24px 24px,
    linear-gradient(90deg, rgba(20, 27, 38, 0.06) 1px, transparent 1px) 0 0 / 24px 24px,
    #fafafa;
}

.dxf-viewer :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
  position: absolute;
  inset: 0;
}

.text-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 5;
  font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB",
    "Helvetica Neue", Arial, sans-serif;
}

.text-overlay :deep(.dxf-text) {
  user-select: none;
  line-height: 1;
  text-shadow: 0 0 2px #fafafa;
}
</style>
