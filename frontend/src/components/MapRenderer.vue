<script setup>
import { ref, reactive, watch, onMounted, onBeforeUnmount, computed } from "vue";
import maplibregl from "maplibre-gl";

// ---------------------------------------------------------------------------
// Render mode: 'webgl' (local MapLibre) | 'server' (WebSocket + PyQGIS)
// ---------------------------------------------------------------------------
const renderMode = ref("webgl"); // 'webgl' | 'server'

// WebSocket state
let ws = null;
const wsStatus = ref("disconnected"); // disconnected | connecting | connected | rendering
const wsProgress = ref(0);
const wsMsg = ref("");
const serverImageUrl     = ref(""); // data URL of latest server-rendered PNG
const serverImagePreview = ref(false); // true=预览帧(模糊)，false=最终高清帧
const serverImageRef     = ref(null);

function connectWs() {
  if (ws && ws.readyState === WebSocket.OPEN) return;
  wsStatus.value = "connecting";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/ws/render`);

  ws.onopen = () => {
    wsStatus.value = "connected";
    wsMsg.value = "WebSocket 已连接";
  };

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "progress") {
        wsProgress.value = msg.pct;
        wsMsg.value = msg.msg;
        wsStatus.value = "rendering";
      } else if (msg.type === "result" && msg.format === "png_base64") {
        serverImageUrl.value = `data:image/png;base64,${msg.data}`;
        serverImagePreview.value = !!msg.is_preview;
        if (!msg.is_preview) {
          wsStatus.value = "connected";
          wsProgress.value = 100;
          wsMsg.value = `渲染完成 (${(msg.size_bytes / 1024).toFixed(0)} KB, ${msg.elapsed_ms}ms)`;
        } else {
          wsMsg.value = `预览就绪，正在加载高清图...`;
        }
      } else if (msg.type === "error") {
        wsMsg.value = `错误: ${msg.msg}`;
        wsStatus.value = "connected";
      } else if (msg.type === "pong") {
        wsMsg.value = "心跳 ✓";
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    wsStatus.value = "disconnected";
    wsMsg.value = "连接断开";
  };
  ws.onerror = () => {
    wsStatus.value = "disconnected";
    wsMsg.value = "连接错误";
  };
}

function disconnectWs() {
  ws?.close();
  ws = null;
}

function requestServerRender() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    connectWs();
    // Retry after connection
    setTimeout(requestServerRender, 800);
    return;
  }
  if (!fileInfo.value?.file_id) {
    wsMsg.value = "请先上传文件";
    return;
  }
  wsProgress.value = 0;
  wsStatus.value = "rendering";
  ws.send(JSON.stringify({
    type: "render",
    file_id: fileInfo.value.file_id,
    width: 1280,
    height: 720,
    style: {
      background: style.background,
      fill_color: style.fillColor,
      fill_opacity: style.fillOpacity,
      stroke_color: style.strokeColor,
      stroke_width: style.strokeWidth,
      label_field: style.labelField,
      label_size: style.labelSize,
      label_color: style.labelColor,
    },
  }));
}

function cancelServerRender() {
  ws?.send(JSON.stringify({ type: "cancel" }));
  wsStatus.value = "connected";
  wsMsg.value = "已取消";
}

function exportServerPng() {
  if (!serverImageUrl.value) return;
  const a = document.createElement("a");
  a.href = serverImageUrl.value;
  a.download = "server_render.png";
  a.click();
}

const wsStatusColor = computed(() => ({
  disconnected: "#e74c3c",
  connecting: "#f39c12",
  connected: "#2ecc71",
  rendering: "#4a90d9",
}[wsStatus.value] || "#888"));

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const mapContainer = ref(null);
const fileInput = ref(null);
const uploading = ref(false);
const uploadError = ref("");
const fileInfo = ref(null);   // { file_id, fields, feature_count, bbox, geometry_types }

let map = null;
const SOURCE_ID = "qgis-data";
const LAYER_IDS = ["fill-layer", "line-layer", "point-layer"];

// Style params — changing any field instantly re-applies to MapLibre
const style = reactive({
  background: "#fafafa",
  fillColor: "#4a90d9",
  fillOpacity: 0.5,
  strokeColor: "#1a5276",
  strokeWidth: 1,
  lineStyle: "solid",       // solid | dash | dot
  markerShape: "circle",    // circle | square | triangle
  markerSize: 6,
  markerColor: "#e74c3c",
  labelField: "",
  labelSize: 12,
  labelColor: "#000000",
  labelHalo: "#ffffff",
  labelHaloWidth: 1,
  preset: "default",
});

const PRESETS = {
  default:    { background:"#fafafa", fillColor:"#4a90d9", fillOpacity:0.5, strokeColor:"#1a5276", strokeWidth:1, markerColor:"#4a90d9", labelColor:"#000000", labelHalo:"#ffffff" },
  autocad:    { background:"#fafafa", fillColor:"#e8f4fd", fillOpacity:0.3, strokeColor:"#1a3050", strokeWidth:0.8, markerColor:"#1a3050", labelColor:"#1a3050", labelHalo:"#fafafa" },
  blueprint:  { background:"#0a1628", fillColor:"#1a6fb5", fillOpacity:0.4, strokeColor:"#4fc3f7", strokeWidth:1.2, markerColor:"#4fc3f7", labelColor:"#4fc3f7", labelHalo:"#0a1628" },
  satellite:  { background:"#1a2a1a", fillColor:"#2ecc71", fillOpacity:0.35, strokeColor:"#27ae60", strokeWidth:1, markerColor:"#f39c12", labelColor:"#ffffff", labelHalo:"#1a2a1a" },
  grayscale:  { background:"#eeeeee", fillColor:"#aaaaaa", fillOpacity:0.5, strokeColor:"#444444", strokeWidth:0.6, markerColor:"#666666", labelColor:"#222222", labelHalo:"#eeeeee" },
  heatmap:    { background:"#0d0d0d", fillColor:"#e74c3c", fillOpacity:0.6, strokeColor:"#c0392b", strokeWidth:0.4, markerColor:"#ff6b6b", labelColor:"#ff6b6b", labelHalo:"#0d0d0d" },
};

const LINEDASH = { solid: [], dash: [4, 2], dot: [1, 2] };

// ---------------------------------------------------------------------------
// Map init
// ---------------------------------------------------------------------------
onMounted(() => {
  map = new maplibregl.Map({
    container: mapContainer.value,
    style: {
      version: 8,
      sources: {},
      layers: [{ id: "bg", type: "background", paint: { "background-color": style.background } }],
    },
    center: [116.4, 39.9],
    zoom: 4,
    attributionControl: false,
  });

  map.addControl(new maplibregl.NavigationControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl(), "bottom-left");
});

// Watch style changes in server mode → auto re-render (debounced)
let _debounceTimer = null;
watch(style, () => {
  if (renderMode.value !== "server" || !fileInfo.value?.file_id) return;
  clearTimeout(_debounceTimer);
  _debounceTimer = setTimeout(requestServerRender, 400);
}, { deep: true });

onBeforeUnmount(() => {
  map?.remove();
  disconnectWs();
  clearTimeout(_debounceTimer);
});

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------
async function onFileChange(e) {
  const file = e.target.files[0];
  if (!file) return;
  uploading.value = true;
  uploadError.value = "";
  fileInfo.value = null;

  const fd = new FormData();
  fd.append("file", file);
  fd.append("srs", "EPSG:4326");

  try {
    const res = await fetch("/api/data/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    const info = await res.json();
    fileInfo.value = info;
    style.labelField = info.fields[0] || "";
    await loadDataToMap(info);
  } catch (err) {
    uploadError.value = String(err);
  } finally {
    uploading.value = false;
  }
}

async function loadDataToMap(info) {
  const geojsonUrl = `/api/data/${info.file_id}`;

  // Remove old layers & source
  for (const id of LAYER_IDS) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);

  map.addSource(SOURCE_ID, { type: "geojson", data: geojsonUrl });

  const types = info.geometry_types || [];
  const hasPolygon = types.some(t => t.includes("Polygon"));
  const hasLine    = types.some(t => t.includes("Line") || t.includes("String"));
  const hasPoint   = types.some(t => t.includes("Point"));

  if (hasPolygon) {
    map.addLayer({
      id: "fill-layer",
      type: "fill",
      source: SOURCE_ID,
      filter: ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
      paint: {
        "fill-color": style.fillColor,
        "fill-opacity": style.fillOpacity,
      },
    });
  }

  if (hasPolygon || hasLine) {
    map.addLayer({
      id: "line-layer",
      type: "line",
      source: SOURCE_ID,
      filter: ["any",
        ["==", ["geometry-type"], "LineString"],
        ["==", ["geometry-type"], "MultiLineString"],
        ["==", ["geometry-type"], "Polygon"],
        ["==", ["geometry-type"], "MultiPolygon"],
      ],
      paint: {
        "line-color": style.strokeColor,
        "line-width": style.strokeWidth,
        "line-dasharray": LINEDASH[style.lineStyle] || [],
      },
    });
  }

  if (hasPoint) {
    map.addLayer({
      id: "point-layer",
      type: "circle",
      source: SOURCE_ID,
      filter: ["any", ["==", ["geometry-type"], "Point"], ["==", ["geometry-type"], "MultiPoint"]],
      paint: {
        "circle-radius": style.markerSize / 2,
        "circle-color": style.markerColor,
        "circle-stroke-color": style.strokeColor,
        "circle-stroke-width": style.strokeWidth,
      },
    });
  }

  applyLabels();
  fitBbox(info.bbox);
}

// ---------------------------------------------------------------------------
// Fit map to bbox
// ---------------------------------------------------------------------------
function fitBbox(bbox) {
  if (!bbox || bbox[0] === bbox[2]) return;
  map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40, duration: 800 });
}

// ---------------------------------------------------------------------------
// Apply style changes instantly (no reload needed)
// ---------------------------------------------------------------------------
function applyStyle() {
  if (!map || !map.getSource(SOURCE_ID)) return;

  // Background
  if (map.getLayer("bg")) {
    map.setPaintProperty("bg", "background-color", style.background);
  }

  // Fill
  if (map.getLayer("fill-layer")) {
    map.setPaintProperty("fill-layer", "fill-color", style.fillColor);
    map.setPaintProperty("fill-layer", "fill-opacity", style.fillOpacity);
  }

  // Line / stroke
  if (map.getLayer("line-layer")) {
    map.setPaintProperty("line-layer", "line-color", style.strokeColor);
    map.setPaintProperty("line-layer", "line-width", style.strokeWidth);
    map.setPaintProperty("line-layer", "line-dasharray", LINEDASH[style.lineStyle] || []);
  }

  // Point
  if (map.getLayer("point-layer")) {
    map.setPaintProperty("point-layer", "circle-radius", style.markerSize / 2);
    map.setPaintProperty("point-layer", "circle-color", style.markerColor);
    map.setPaintProperty("point-layer", "circle-stroke-color", style.strokeColor);
    map.setPaintProperty("point-layer", "circle-stroke-width", style.strokeWidth);
  }

  applyLabels();
}

function applyLabels() {
  if (!map) return;
  if (map.getLayer("label-layer")) map.removeLayer("label-layer");
  if (!style.labelField || !map.getSource(SOURCE_ID)) return;

  map.addLayer({
    id: "label-layer",
    type: "symbol",
    source: SOURCE_ID,
    layout: {
      "text-field": ["get", style.labelField],
      "text-size": style.labelSize,
      "text-anchor": "bottom",
      "text-offset": [0, -0.5],
      "text-allow-overlap": false,
    },
    paint: {
      "text-color": style.labelColor,
      "text-halo-color": style.labelHalo,
      "text-halo-width": style.labelHaloWidth,
    },
  });
}

// Watch every style property → instant re-apply
watch(style, applyStyle, { deep: true });

// Apply preset
function applyPreset(name) {
  const p = PRESETS[name];
  if (!p) return;
  Object.assign(style, p);
  style.preset = name;
}

// Export current view as PNG
function exportPng() {
  const canvas = map.getCanvas();
  const url = canvas.toDataURL("image/png");
  const a = document.createElement("a");
  a.href = url;
  a.download = "map_render.png";
  a.click();
}

// Export style as JSON
function exportStyleJson() {
  const blob = new Blob([JSON.stringify(style, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "style_params.json";
  a.click();
}
</script>

<template>
  <div class="map-renderer">
    <!-- ── Sidebar ── -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2>实时 2D 渲染器</h2>
        <p class="sub">WebGL · 16ms 刷新</p>
      </div>

      <!-- Upload -->
      <section class="panel">
        <h3>数据文件</h3>
        <button class="btn-upload" @click="fileInput.click()" :disabled="uploading">
          {{ uploading ? "上传中…" : "上传文件" }}
        </button>
        <input ref="fileInput" type="file"
          accept=".dxf,.shp,.geojson,.json,.kml,.gpkg,.csv"
          style="display:none" @change="onFileChange" />
        <p v-if="uploadError" class="error">{{ uploadError }}</p>
        <div v-if="fileInfo" class="info-box">
          <b>{{ fileInfo.original_name }}</b><br>
          要素数: {{ fileInfo.feature_count }}<br>
          类型: {{ fileInfo.geometry_types?.join(", ") }}<br>
          字段: {{ fileInfo.fields?.join(", ") || "无" }}
        </div>
      </section>

      <!-- Preset -->
      <section class="panel">
        <h3>预设样式</h3>
        <div class="preset-grid">
          <button v-for="(_, name) in PRESETS" :key="name"
            :class="['preset-btn', { active: style.preset === name }]"
            @click="applyPreset(name)">
            {{ name }}
          </button>
        </div>
      </section>

      <!-- Color & Fill -->
      <section class="panel">
        <h3>颜色 / 填充</h3>
        <label>背景色
          <input type="color" v-model="style.background" />
        </label>
        <label>填充色
          <input type="color" v-model="style.fillColor" />
        </label>
        <label>填充透明度 {{ Math.round(style.fillOpacity * 100) }}%
          <input type="range" min="0" max="1" step="0.01" v-model.number="style.fillOpacity" />
        </label>
        <label>线/边框色
          <input type="color" v-model="style.strokeColor" />
        </label>
        <label>线宽 {{ style.strokeWidth }}px
          <input type="range" min="0.2" max="10" step="0.1" v-model.number="style.strokeWidth" />
        </label>
        <label>线型
          <select v-model="style.lineStyle">
            <option value="solid">实线</option>
            <option value="dash">虚线</option>
            <option value="dot">点线</option>
          </select>
        </label>
      </section>

      <!-- Point -->
      <section class="panel">
        <h3>点符号</h3>
        <label>点颜色
          <input type="color" v-model="style.markerColor" />
        </label>
        <label>点大小 {{ style.markerSize }}px
          <input type="range" min="2" max="30" step="1" v-model.number="style.markerSize" />
        </label>
      </section>

      <!-- Labels -->
      <section class="panel">
        <h3>标注</h3>
        <label>标注字段
          <select v-model="style.labelField">
            <option value="">（不标注）</option>
            <option v-for="f in (fileInfo?.fields || [])" :key="f" :value="f">{{ f }}</option>
          </select>
        </label>
        <label>字号 {{ style.labelSize }}px
          <input type="range" min="8" max="32" step="1" v-model.number="style.labelSize" />
        </label>
        <label>标注颜色
          <input type="color" v-model="style.labelColor" />
        </label>
        <label>描边色
          <input type="color" v-model="style.labelHalo" />
        </label>
        <label>描边宽 {{ style.labelHaloWidth }}px
          <input type="range" min="0" max="4" step="0.5" v-model.number="style.labelHaloWidth" />
        </label>
      </section>

      <!-- Render Mode -->
      <section class="panel">
        <h3>渲染引擎</h3>
        <div class="mode-switch">
          <button :class="['mode-btn', { active: renderMode === 'webgl' }]" @click="renderMode = 'webgl'">
            ⚡ WebGL 本地
          </button>
          <button :class="['mode-btn', { active: renderMode === 'server' }]"
            @click="renderMode = 'server'; connectWs()">
            🖥 服务端 WS
          </button>
        </div>
        <!-- WS status -->
        <div v-if="renderMode === 'server'" class="ws-status">
          <span class="ws-dot" :style="{ background: wsStatusColor }"></span>
          <span class="ws-label">{{ wsStatus }}</span>
          <span class="ws-msg">{{ wsMsg }}</span>
        </div>
        <div v-if="renderMode === 'server' && wsStatus === 'rendering'" class="progress-bar">
          <div class="progress-fill" :style="{ width: wsProgress + '%' }"></div>
          <span>{{ wsProgress }}%</span>
        </div>
        <template v-if="renderMode === 'server'">
          <button class="btn-action" @click="requestServerRender" :disabled="!fileInfo || wsStatus === 'rendering'">
            立即渲染
          </button>
          <button class="btn-action" @click="cancelServerRender" :disabled="wsStatus !== 'rendering'">
            取消
          </button>
          <button class="btn-action" @click="exportServerPng" :disabled="!serverImageUrl">
            导出 PNG
          </button>
        </template>
      </section>

      <!-- Export (WebGL mode) -->
      <section class="panel" v-if="renderMode === 'webgl'">
        <h3>导出</h3>
        <button class="btn-action" @click="exportPng">导出 PNG</button>
        <button class="btn-action" @click="exportStyleJson">导出样式 JSON</button>
      </section>
    </aside>

    <!-- ── Map Canvas (WebGL mode) ── -->
    <div class="map-wrap" ref="mapContainer" v-show="renderMode === 'webgl'"></div>

    <!-- ── Server Render Result (WS mode) ── -->
    <div class="server-canvas" v-show="renderMode === 'server'">
      <img v-if="serverImageUrl" ref="serverImageRef" :src="serverImageUrl"
           :class="['server-img', { 'is-preview': serverImagePreview }]" />
      <div v-else class="server-placeholder">
        <div class="ph-icon">🖥</div>
        <div>切换到「服务端 WS」模式后，上传文件并点击「立即渲染」</div>
        <div class="ph-sub">PyQGIS 渲染结果通过 WebSocket 实时推送</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.map-renderer {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* ── Sidebar ── */
.sidebar {
  width: 260px;
  min-width: 240px;
  background: #1a1f2e;
  color: #d0d8e8;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  z-index: 10;
  font-size: 13px;
}

.sidebar-header {
  padding: 16px 14px 10px;
  border-bottom: 1px solid #2d3550;
}
.sidebar-header h2 { margin: 0; font-size: 15px; color: #fff; }
.sidebar-header .sub { margin: 2px 0 0; color: #5a6a8a; font-size: 11px; }

.panel {
  padding: 12px 14px;
  border-bottom: 1px solid #2d3550;
}
.panel h3 {
  margin: 0 0 8px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #5a6a8a;
}

label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 7px;
  color: #c0cce0;
  font-size: 12px;
}
label input[type="color"] {
  width: 36px; height: 22px;
  border: 1px solid #3a4a60; border-radius: 3px;
  cursor: pointer; background: none; padding: 0;
}
label input[type="range"] {
  width: 100px; accent-color: #4a90d9;
}
label select {
  background: #252d40; color: #d0d8e8;
  border: 1px solid #3a4a60; border-radius: 3px;
  padding: 2px 6px; font-size: 12px;
}

/* Presets */
.preset-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
}
.preset-btn {
  padding: 5px 4px;
  font-size: 11px;
  border: 1px solid #3a4a60;
  border-radius: 4px;
  background: #252d40;
  color: #8a9ab8;
  cursor: pointer;
  transition: all 0.15s;
  text-transform: capitalize;
}
.preset-btn:hover { background: #2d3f60; color: #fff; }
.preset-btn.active { background: #4a90d9; color: #fff; border-color: #4a90d9; }

/* Buttons */
.btn-upload {
  width: 100%; padding: 8px;
  background: #4a90d9; color: #fff;
  border: none; border-radius: 5px;
  cursor: pointer; font-size: 13px;
  margin-bottom: 8px;
}
.btn-upload:disabled { background: #3a4a60; cursor: not-allowed; }
.btn-action {
  width: 100%; padding: 6px;
  background: #252d40; color: #c0cce0;
  border: 1px solid #3a4a60; border-radius: 4px;
  cursor: pointer; font-size: 12px;
  margin-bottom: 5px;
}
.btn-action:hover { background: #2d3f60; color: #fff; }

.info-box {
  margin-top: 8px;
  padding: 8px;
  background: #252d40;
  border-radius: 4px;
  font-size: 11px;
  color: #8a9ab8;
  line-height: 1.6;
}
.info-box b { color: #d0d8e8; }

.error {
  color: #e74c3c;
  font-size: 11px;
  margin: 4px 0;
  word-break: break-all;
}

/* ── Map ── */
.map-wrap {
  flex: 1;
  position: relative;
}

/* Mode switch */
.mode-switch {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}
.mode-btn {
  flex: 1;
  padding: 6px 4px;
  font-size: 11px;
  border: 1px solid #3a4a60;
  border-radius: 4px;
  background: #252d40;
  color: #8a9ab8;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-btn:hover { background: #2d3f60; color: #fff; }
.mode-btn.active { background: #1a6fb5; color: #fff; border-color: #4fc3f7; }

/* WS status */
.ws-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  margin-bottom: 6px;
}
.ws-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ws-label { color: #d0d8e8; font-weight: bold; }
.ws-msg { color: #5a6a8a; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Progress */
.progress-bar {
  position: relative;
  height: 16px;
  background: #1a2030;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
}
.progress-fill {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  background: linear-gradient(90deg, #1a6fb5, #4fc3f7);
  transition: width 0.3s ease;
  border-radius: 8px;
}
.progress-bar span {
  position: relative;
  z-index: 1;
  font-size: 10px;
  color: #fff;
  padding: 0 8px;
}

/* Server canvas */
.server-canvas {
  flex: 1;
  background: #0d1117;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}
.server-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: filter 0.4s ease, transform 0.4s ease;
}
.server-img.is-preview {
  filter: blur(6px);
  transform: scale(1.02);
  image-rendering: pixelated;
}
.server-placeholder {
  text-align: center;
  color: #3a4a60;
  font-size: 13px;
  line-height: 2;
}
.server-placeholder .ph-icon { font-size: 48px; margin-bottom: 12px; opacity: 0.4; }
.server-placeholder .ph-sub { font-size: 11px; color: #2a3a50; margin-top: 4px; }
</style>
