# DXF 编辑器前端示例

## 方案说明

### 核心思路
**前端驱动，后端只负责文件存储和生成**

- ✅ 前端直接下载并解析 DXF 文件
- ✅ 用户点击实体时显示编辑面板
- ✅ 只发送修改的参数到后端（几条到几十条）
- ✅ 不需要数据库存储 78918 个参数

### 性能优势

| 指标 | 后端存储方案 | 前端驱动方案 |
|------|--------------|--------------|
| 数据库存储 | 78918条/模板 | 0条 |
| 查询速度 | 1-10秒 | 毫秒级 |
| 传输数据量 | 几MB（全部参数） | 几KB（修改的参数） |
| 用户体验 | 需要等待加载 | 即点即改 |

---

## 安装依赖

```bash
npm install three dxf-parser
# 或
yarn add three dxf-parser
```

---

## 使用方法

### 1. 基本使用

```jsx
import DxfEditor from './DxfEditor';

function App() {
  const templateId = 'your-template-id';
  
  return (
    <div>
      <h1>DXF 模板编辑器</h1>
      <DxfEditor templateId={templateId} />
    </div>
  );
}
```

### 2. 完整示例

```jsx
import React, { useState } from 'react';
import DxfEditor from './DxfEditor';

function TemplateManager() {
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  
  // 加载模板列表
  useEffect(() => {
    fetch('/api/template/list?is_official=true')
      .then(res => res.json())
      .then(data => setTemplates(data.data.records));
  }, []);
  
  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      {/* 左侧：模板列表 */}
      <div style={{ width: '200px', borderRight: '1px solid #ccc', padding: '10px' }}>
        <h3>模板列表</h3>
        {templates.map(t => (
          <div
            key={t.id}
            onClick={() => setSelectedTemplate(t.id)}
            style={{
              padding: '10px',
              cursor: 'pointer',
              background: selectedTemplate === t.id ? '#e0e0e0' : 'white'
            }}
          >
            {t.name}
          </div>
        ))}
      </div>
      
      {/* 右侧：编辑器 */}
      <div style={{ flex: 1 }}>
        {selectedTemplate ? (
          <DxfEditor templateId={selectedTemplate} />
        ) : (
          <div style={{ padding: '20px' }}>
            请选择一个模板
          </div>
        )}
      </div>
    </div>
  );
}
```

---

## API 接口

### 1. 获取 DXF 文件

**GET** `/api/template/v2/file?id={templateId}`

返回原始 DXF 文件（重定向到 MinIO）

### 2. 生成新 DXF

**POST** `/api/template/v2/generate`

**请求参数**：
- `template_id`: 模板 ID
- `modifications`: 修改内容（JSON 字符串）

**modifications 格式**：
```json
[
  {
    "handle": "1A0",
    "type": "LINE",
    "changes": {
      "start": [100, 200, 0],
      "end": [300, 400, 0]
    }
  },
  {
    "handle": "1B5",
    "type": "TEXT",
    "changes": {
      "text": "新文字",
      "height": 5.0
    }
  }
]
```

**响应**：
```json
{
  "code": 0,
  "message": "生成成功",
  "data": {
    "filename": "template_modified.dxf",
    "file_url": "http://minio.../generated.dxf",
    "modified_count": 2
  }
}
```

---

## 支持的实体类型

### 当前支持

| 实体类型 | 可编辑参数 | 状态 |
|----------|------------|------|
| LINE | start, end | ✅ 完整支持 |
| CIRCLE | center, radius | ✅ 完整支持 |
| ARC | center, radius, start_angle, end_angle | ✅ 完整支持 |
| TEXT | text, insert, height | ✅ 完整支持 |
| MTEXT | text, insert, char_height | ✅ 完整支持 |
| LWPOLYLINE | points | ✅ 完整支持 |
| INSERT | insert, xscale, yscale, rotation | ✅ 完整支持 |

### 扩展支持

可以轻松添加更多实体类型，只需：

1. 在前端添加渲染逻辑（`renderDxfEntities`）
2. 在前端添加编辑面板（`EntityEditPanel`）
3. 在后端添加修改逻辑（`dxf_frontend_api.py`）

---

## 性能优化建议

### 1. 大文件处理

```javascript
// 对于超大 DXF 文件，可以分批渲染
function renderDxfEntities(dxf, scene) {
  const batchSize = 1000;
  let index = 0;
  
  function renderBatch() {
    const end = Math.min(index + batchSize, dxf.entities.length);
    
    for (let i = index; i < end; i++) {
      renderEntity(dxf.entities[i], scene);
    }
    
    index = end;
    
    if (index < dxf.entities.length) {
      requestAnimationFrame(renderBatch);
    }
  }
  
  renderBatch();
}
```

### 2. 图层过滤

```javascript
// 只渲染可见图层
function renderDxfEntities(dxf, scene, visibleLayers) {
  dxf.entities
    .filter(e => visibleLayers.includes(e.layer))
    .forEach(entity => renderEntity(entity, scene));
}
```

### 3. LOD (Level of Detail)

```javascript
// 根据缩放级别调整细节
function renderCircle(entity, camera) {
  const distance = camera.position.distanceTo(entity.center);
  const segments = distance > 100 ? 16 : 32; // 远处用更少的段数
  
  const geometry = new THREE.CircleGeometry(entity.radius, segments);
  // ...
}
```

---

## 常见问题

### Q1: DXF 文件太大，加载慢怎么办？

**A**: 
1. 使用 Web Worker 解析 DXF
2. 分批渲染实体
3. 添加加载进度条

```javascript
// 使用 Web Worker
const worker = new Worker('dxf-parser-worker.js');
worker.postMessage({ dxfText });
worker.onmessage = (e) => {
  const dxf = e.data;
  renderDxfEntities(dxf, scene);
};
```

### Q2: 如何支持更多实体类型？

**A**: 参考现有代码，添加对应的渲染和编辑逻辑

```javascript
// 1. 添加渲染逻辑
else if (entity.type === 'ELLIPSE') {
  const curve = new THREE.EllipseCurve(
    entity.center.x, entity.center.y,
    entity.majorAxisEndPoint.x, entity.minorAxisRatio,
    0, 2 * Math.PI
  );
  // ...
}

// 2. 添加编辑面板
if (entity.type === 'ELLIPSE') {
  return (
    <div>
      <h3>椭圆</h3>
      <input ... />
    </div>
  );
}
```

### Q3: 如何实现撤销/重做？

**A**: 使用状态历史

```javascript
const [history, setHistory] = useState([]);
const [historyIndex, setHistoryIndex] = useState(-1);

function handleParamChange(handle, param, value) {
  const newMods = { ...modifications, [handle]: { ...modifications[handle], [param]: value } };
  
  // 保存历史
  const newHistory = history.slice(0, historyIndex + 1);
  newHistory.push(newMods);
  setHistory(newHistory);
  setHistoryIndex(newHistory.length - 1);
  
  setModifications(newMods);
}

function undo() {
  if (historyIndex > 0) {
    setHistoryIndex(historyIndex - 1);
    setModifications(history[historyIndex - 1]);
  }
}

function redo() {
  if (historyIndex < history.length - 1) {
    setHistoryIndex(historyIndex + 1);
    setModifications(history[historyIndex + 1]);
  }
}
```

---

## 总结

### 优势

1. ✅ **无需数据库存储参数**：节省存储空间和查询时间
2. ✅ **极快的响应速度**：前端直接操作，毫秒级响应
3. ✅ **灵活的扩展性**：轻松添加新的实体类型
4. ✅ **优秀的用户体验**：所见即所得，实时预览

### 适用场景

- ✅ DXF 模板编辑
- ✅ 参数化设计
- ✅ 在线 CAD 编辑器
- ✅ 工程图纸定制

### 技术栈

- React: UI 框架
- Three.js: 3D 渲染
- dxf-parser: DXF 解析
- FastAPI: 后端 API
- MinIO: 文件存储
