<script setup>
import { ref, computed, reactive } from "vue";
import DxfViewer from "./components/DxfViewer.vue";
import MapRenderer from "./components/MapRenderer.vue";

const activeTab = ref("dxf"); // 'dxf' | 'renderer'

const viewer = ref(null);
const fileInfo = ref(null); // { name, size, source: 'dxf' | 'dwg' }
const layers = ref([]);      // [{ name, visible, color }]
const loading = ref(false);
const errorMsg = ref("");
const statusMsg = ref("拖拽 DXF / DWG 文件到画布，或点击下方按钮选择");
const stats = reactive({ entities: 0, width: 0, height: 0 });
const measure = ref({ enabled: false, distance: null, angle: null });
const selectionList = ref([]);
const editCount = ref(0);

const hasFile = computed(() => !!fileInfo.value);

async function handleFile(file) {
  if (!file) return;
  errorMsg.value = "";
  loading.value = true;
  statusMsg.value = `正在加载 ${file.name} ...`;

  const lower = file.name.toLowerCase();
  try {
    let dxfFile = file;
    let source = "dxf";

    if (lower.endsWith(".dwg")) {
      source = "dwg";
      statusMsg.value = "正在将 DWG 转换为 DXF ...";
      const fd = new FormData();
      fd.append("file", file);
      const resp = await fetch("/api/convert/dwg", { method: "POST", body: fd });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`DWG 转换失败: ${resp.status} ${text}`);
      }
      const blob = await resp.blob();
      dxfFile = new File([blob], file.name.replace(/\.dwg$/i, ".dxf"), {
        type: "application/dxf",
      });
    } else if (!lower.endsWith(".dxf")) {
      throw new Error("仅支持 .dxf / .dwg 文件");
    }

    const result = await viewer.value.loadFile(dxfFile);
    fileInfo.value = {
      name: file.name,
      size: file.size,
      source,
    };
    layers.value = result.layers.map((l) => ({ ...l }));
    stats.entities = result.entityCount;
    stats.width = Math.round(result.width);
    stats.height = Math.round(result.height);
    statusMsg.value = `${file.name} 加载完成`;
  } catch (e) {
    console.error(e);
    errorMsg.value = e.message || String(e);
    statusMsg.value = "加载失败";
  } finally {
    loading.value = false;
  }
}

function pickFile() {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".dxf,.dwg";
  inp.onchange = (e) => handleFile(e.target.files[0]);
  inp.click();
}

function onDrop(e) {
  e.preventDefault();
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
}

function toggleLayer(layer) {
  layer.visible = !layer.visible;
  viewer.value.setLayerVisible(layer.name, layer.visible);
}

function toggleAll(show) {
  for (const l of layers.value) {
    l.visible = show;
    viewer.value.setLayerVisible(l.name, show);
  }
}

function zoomExtent() {
  viewer.value?.zoomToExtent();
}
function zoomIn() {
  viewer.value?.zoomBy(1.25);
}
function zoomOut() {
  viewer.value?.zoomBy(1 / 1.25);
}
function toggleMeasure() {
  measure.value.enabled = !measure.value.enabled;
  viewer.value?.setMeasureEnabled(measure.value.enabled);
}

function exportPng() {
  viewer.value?.exportPng(fileInfo.value?.name?.replace(/\.(dxf|dwg)$/i, "") || "render");
}

async function exportEdited(fmt) {
  if (!fileInfo.value) return;
  loading.value = true;
  statusMsg.value = `正在导出 ${fmt.toUpperCase()} ...`;
  errorMsg.value = "";
  try {
    await viewer.value.exportEdited(fmt);
    statusMsg.value = `${fmt.toUpperCase()} 已下载`;
  } catch (e) {
    errorMsg.value = e.message || String(e);
    statusMsg.value = "导出失败";
  } finally {
    loading.value = false;
  }
}

function deleteSelection() {
  viewer.value?.deleteSelection();
}

function onSelectionChange(list) {
  selectionList.value = list;
}

function onEditsChange(list) {
  editCount.value = list.length;
}

function formatBytes(n) {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}
</script>

<template>
  <div class="app" @dragover.prevent @drop="onDrop">
    <!-- Top bar -->
    <header class="topbar">
      <div class="brand">
        <span class="dot"></span>
        <span class="title">DXF / DWG Viewer</span>
        <span class="sub">矢量无损 · three.js 渲染</span>
      </div>
      <!-- Tab switcher -->
      <div class="tab-bar">
        <button :class="['tab-btn', { active: activeTab === 'dxf' }]" @click="activeTab = 'dxf'">DXF 编辑器</button>
        <button :class="['tab-btn', { active: activeTab === 'renderer' }]" @click="activeTab = 'renderer'">实时渲染器</button>
      </div>
      <div class="actions">
        <button @click="pickFile" class="primary">打开文件</button>
        <button @click="zoomExtent" :disabled="!hasFile">适配视图</button>
        <button @click="zoomIn" :disabled="!hasFile">＋</button>
        <button @click="zoomOut" :disabled="!hasFile">－</button>
        <button
          @click="toggleMeasure"
          :disabled="!hasFile"
          :class="{ primary: measure.enabled }"
        >
          测量
        </button>
        <button
          @click="deleteSelection"
          :disabled="!selectionList.length"
          class="danger"
        >
          删除选中 ({{ selectionList.length }})
        </button>
        <span class="divider"></span>
        <button @click="exportPng" :disabled="!hasFile">PNG</button>
        <button @click="exportEdited('dxf')" :disabled="!hasFile" class="accent">
          导出 DXF<span v-if="editCount" class="badge">{{ editCount }}</span>
        </button>
        <button @click="exportEdited('dwg')" :disabled="!hasFile" class="accent">
          导出 DWG
        </button>
      </div>
    </header>

    <!-- Main layout -->
    <div class="layout" v-show="activeTab === 'dxf'">
      <!-- Left sidebar: layers -->
      <aside class="sidebar">
        <div class="panel">
          <div class="panel-title">
            <span>图层</span>
            <span class="counter">{{ layers.length }}</span>
          </div>
          <div class="panel-body">
            <div v-if="!layers.length" class="empty">无数据</div>
            <div v-else>
              <div class="layer-actions">
                <button @click="toggleAll(true)">全部显示</button>
                <button @click="toggleAll(false)">全部隐藏</button>
              </div>
              <ul class="layer-list">
                <li
                  v-for="layer in layers"
                  :key="layer.name"
                  :class="{ hidden: !layer.visible }"
                  @click="toggleLayer(layer)"
                >
                  <span
                    class="swatch"
                    :style="{ background: layer.color || '#8796ac' }"
                  ></span>
                  <span class="layer-name" :title="layer.name">{{ layer.name }}</span>
                  <span class="layer-eye">{{ layer.visible ? "●" : "○" }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">文件信息</div>
          <div class="panel-body info">
            <template v-if="fileInfo">
              <div><span class="k">名称</span><span class="v">{{ fileInfo.name }}</span></div>
              <div><span class="k">大小</span><span class="v">{{ formatBytes(fileInfo.size) }}</span></div>
              <div><span class="k">源格式</span><span class="v">{{ fileInfo.source.toUpperCase() }}</span></div>
              <div><span class="k">实体数</span><span class="v">{{ stats.entities }}</span></div>
              <div><span class="k">包围盒</span><span class="v">{{ stats.width }} × {{ stats.height }}</span></div>
            </template>
            <template v-else>
              <div class="empty">尚未加载文件</div>
            </template>
          </div>
        </div>

        <div class="panel" v-if="measure.enabled && measure.distance !== null">
          <div class="panel-title">测量结果</div>
          <div class="panel-body info">
            <div><span class="k">距离</span><span class="v">{{ measure.distance.toFixed(3) }}</span></div>
            <div v-if="measure.angle !== null">
              <span class="k">角度</span><span class="v">{{ measure.angle.toFixed(2) }}°</span>
            </div>
          </div>
        </div>

        <div class="panel" v-if="selectionList.length">
          <div class="panel-title">
            <span>选中实体</span>
            <span class="counter">{{ selectionList.length }}</span>
          </div>
          <div class="panel-body info">
            <div v-for="(s, i) in selectionList" :key="i">
              <span class="k">{{ s.type }}</span>
              <span class="v">#{{ s.handle }} · {{ s.layer }}</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">操作提示</div>
          <div class="panel-body tips">
            <div>· <b>左键</b> 拖拽空白处 = 平移视图</div>
            <div>· <b>滚轮</b> = 缩放</div>
            <div>· <b>左键</b> 实体 = 选中（拖动可移动）</div>
            <div>· <b>双击</b> 文字 = 修改文字</div>
            <div>· <b>Delete</b> = 删除选中</div>
            <div>· <b>Esc</b> = 取消选择</div>
          </div>
        </div>
      </aside>

      <!-- Viewer -->
      <main class="viewer-wrap">
        <DxfViewer
          ref="viewer"
          @measure="(m) => Object.assign(measure, m)"
          @selection="onSelectionChange"
          @edits="onEditsChange"
        />
        <div v-if="!hasFile && !loading" class="drop-hint">
          <div class="drop-box">
            <div class="drop-icon">📐</div>
            <div class="drop-title">拖拽 DXF / DWG 到此处</div>
            <div class="drop-sub">或点击右上角「打开文件」</div>
          </div>
        </div>
        <div v-if="loading" class="loading-veil">
          <div class="spinner"></div>
          <div class="loading-text">{{ statusMsg }}</div>
        </div>
      </main>
    </div>

    <!-- 实时渲染器 Tab -->
    <div v-show="activeTab === 'renderer'" class="renderer-tab">
      <MapRenderer />
    </div>

    <!-- Status bar -->
    <footer class="statusbar">
      <span :class="{ err: !!errorMsg }">{{ errorMsg || statusMsg }}</span>
    </footer>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.tab-bar {
  display: flex;
  gap: 4px;
}
.tab-btn {
  padding: 5px 14px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}
.tab-btn:hover { background: var(--border); color: var(--fg); }
.tab-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }

.renderer-tab {
  flex: 1;
  overflow: hidden;
  display: flex;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  gap: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand .dot {
  width: 10px;
  height: 10px;
  background: var(--accent-2);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--accent-2);
}
.brand .title {
  font-weight: 600;
  font-size: 15px;
}
.brand .sub {
  color: var(--text-dim);
  font-size: 12px;
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.divider {
  width: 1px;
  height: 22px;
  background: var(--border);
  margin: 0 4px;
}

.actions :deep(button.danger),
.actions button.danger {
  background: rgba(255, 80, 80, 0.12);
  border-color: rgba(255, 80, 80, 0.4);
  color: #ff8080;
}
.actions button.danger:hover:not(:disabled) {
  background: rgba(255, 80, 80, 0.22);
  border-color: var(--danger);
}

.actions button.accent {
  background: rgba(124, 240, 197, 0.12);
  border-color: rgba(124, 240, 197, 0.4);
  color: var(--accent-2);
}
.actions button.accent:hover:not(:disabled) {
  background: rgba(124, 240, 197, 0.22);
  border-color: var(--accent-2);
}

.actions .badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 7px;
  background: var(--accent-2);
  color: #07120c;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 700;
}

.layout {
  display: flex;
  flex: 1;
  min-height: 0;
}

.sidebar {
  width: 280px;
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 12px;
  gap: 12px;
}

.panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  overflow: hidden;
}
.panel-title {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--panel-hover);
  font-size: 13px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}
.panel-title .counter {
  color: var(--text-dim);
  font-weight: 400;
}
.panel-body {
  padding: 8px;
  max-height: 300px;
  overflow-y: auto;
}
.empty {
  color: var(--text-dim);
  font-size: 12px;
  text-align: center;
  padding: 12px 0;
}

.layer-actions {
  display: flex;
  gap: 6px;
  padding: 4px 4px 8px;
}
.layer-actions button {
  flex: 1;
  font-size: 12px;
  padding: 4px 6px;
}

.layer-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.layer-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.1s;
}
.layer-list li:hover {
  background: var(--panel-hover);
}
.layer-list li.hidden {
  opacity: 0.35;
}
.swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  flex-shrink: 0;
}
.layer-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.layer-eye {
  color: var(--text-dim);
}

.info div {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 3px 4px;
}
.info .k {
  color: var(--text-dim);
}
.info .v {
  font-family: "SF Mono", Menlo, monospace;
  max-width: 170px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tips {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-dim);
}
.tips b {
  color: var(--text);
  font-weight: 600;
}

.viewer-wrap {
  flex: 1;
  position: relative;
  background: #fafafa;
  overflow: hidden;
}

.drop-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.drop-box {
  border: 2px dashed #b8c2d4;
  border-radius: 14px;
  padding: 30px 50px;
  text-align: center;
  background: rgba(255, 255, 255, 0.85);
  color: #3a4a60;
  backdrop-filter: blur(4px);
}
.drop-box .drop-sub { color: #6a7a90; }
.drop-icon {
  font-size: 40px;
}
.drop-title {
  font-size: 18px;
  font-weight: 600;
  margin-top: 10px;
}
.drop-sub {
  color: var(--text-dim);
  font-size: 13px;
  margin-top: 4px;
}

.loading-veil {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(10, 14, 22, 0.7);
  gap: 14px;
  z-index: 10;
}
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.loading-text {
  color: var(--text-dim);
  font-size: 13px;
}

.statusbar {
  padding: 6px 14px;
  font-size: 12px;
  color: var(--text-dim);
  background: var(--panel);
  border-top: 1px solid var(--border);
}
.statusbar .err {
  color: var(--danger);
}
</style>
