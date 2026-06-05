# DXF 编辑器 API 文档

## 概述

基于 FastAPI + QGIS 的 DXF 文件在线编辑系统，支持大文件高效处理、图像预览、实体点选编辑。

**版本**: 1.0  
**基础 URL**: `http://localhost:8080/api`  
**编码**: GBK (cp936) for R12 DXF  
**支持的实体类型**: 10 种（覆盖率 100%）

---

## 目录

1. [快速开始](#快速开始)
2. [API 端点](#api-端点)
3. [支持的实体类型](#支持的实体类型)
4. [数据结构](#数据结构)
5. [使用示例](#使用示例)
6. [工具脚本](#工具脚本)
7. [错误处理](#错误处理)

---

## 快速开始

### 启动服务

```bash
cd /Users/czy/Downloads/QGIS/dxf_render_service
NETWORK_MODE=external bash run_qgis_mac.sh
```

服务将在 `http://0.0.0.0:8080` 启动

### 前端访问

```bash
cd frontend_example
npm install
npm start
```

前端将在 `http://localhost:3000` 启动

---

## API 端点

### 1. 生成预览图

**端点**: `POST /template/image/preview`

**描述**: 上传 DXF 文件，生成预览图像

**请求体**:
```json
{
  "template": {
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  }
}
```

**响应**:
```json
{
  "preview_url": "http://database.yuxindazhineng.com/bucket/preview.png",
  "width": 1920,
  "height": 1080
}
```

**状态码**:
- `200`: 成功
- `400`: 请求参数错误
- `500`: 服务器错误

---

### 2. 获取 DXF 范围

**端点**: `POST /template/image/extent`

**描述**: 获取 DXF 文件的边界框坐标，用于坐标转换

**请求体**:
```json
{
  "template": {
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  }
}
```

**响应**:
```json
{
  "min_x": 0.0,
  "min_y": 0.0,
  "max_x": 100000.0,
  "max_y": 50000.0
}
```

**用途**: 前端使用此数据将图片像素坐标转换为 DXF 坐标

---

### 3. 查询点击位置的实体

**端点**: `POST /template/image/entity-at`

**描述**: 根据 DXF 坐标查找附近的实体

**请求体**:
```json
{
  "template": {
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  },
  "x": 65432.51,
  "y": 6149.49,
  "tolerance": 500.0
}
```

**参数说明**:
- `x`: DXF X 坐标（非像素坐标）
- `y`: DXF Y 坐标（非像素坐标）
- `tolerance`: 搜索容差（DXF 单位）

**响应**:
```json
{
  "entities": [
    {
      "handle": "37A64",
      "type": "CIRCLE",
      "layer": "测试道路纵断面设计线",
      "distance": 0.51,
      "params": {
        "color": {
          "value": 60,
          "editable": true,
          "type": "number",
          "description": "颜色索引（0-256，256=随层）",
          "min": 0,
          "max": 256
        },
        "lineweight": {
          "value": -1,
          "editable": true,
          "type": "number",
          "description": "线宽（-1=随层，-2=随块，-3=默认）"
        },
        "center": {
          "value": [65432.51, 6149.49, 0.0],
          "editable": true,
          "type": "point",
          "description": "圆心坐标 [x, y, z]"
        },
        "radius": {
          "value": 1.0,
          "editable": true,
          "type": "number",
          "description": "半径",
          "min": 0.001
        }
      }
    }
  ],
  "total_entities": 39775
}
```

**返回实体按距离排序**，最近的在前

---

### 4. 应用修改并生成新 DXF

**端点**: `POST /template/image/generate`

**描述**: 应用实体修改，生成新的 R12 DXF 文件

**请求体**:
```json
{
  "template": {
    "name": "测试道路",
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  },
  "modifications": [
    {
      "handle": "37A64",
      "changes": {
        "center": [65500.0, 6200.0, 0.0],
        "radius": 2.0,
        "color": 1
      }
    },
    {
      "handle": "347A7",
      "changes": {
        "start": [65500.0, 6000.0, 0.0],
        "color": 60
      }
    }
  ]
}
```

**响应**:
```json
{
  "dxf_url": "http://database.yuxindazhineng.com/bucket/测试道路_modified.dxf",
  "modified_count": 2
}
```

**注意**:
- 生成的 DXF 为 R12 格式
- 使用 GBK (cp936) 编码
- 支持中文图层和文字

---

## 支持的实体类型

### 完整支持列表（10种）

| # | 实体类型 | 中文名 | 可编辑参数 |
|---|---------|--------|-----------|
| 1 | LINE | 直线 | start, end, color, lineweight |
| 2 | CIRCLE | 圆 | center, radius, color, lineweight |
| 3 | ARC | 圆弧 | center, radius, start_angle, end_angle, color, lineweight |
| 4 | TEXT/MTEXT | 文字 | text, insert, height, color, lineweight |
| 5 | POINT | 点 | location, color, lineweight |
| 6 | ELLIPSE | 椭圆 | center, major_axis, ratio, start_param, end_param, color, lineweight |
| 7 | SPLINE | 样条曲线 | control_points, color, lineweight |
| 8 | LWPOLYLINE | 多段线 | vertices, closed, const_width, color, lineweight |
| 9 | INSERT | 块引用 | insert, xscale, yscale, zscale, rotation, color, lineweight |
| 10 | LEADER | 引线 | vertices, has_arrowhead, color, lineweight |

### 通用属性（所有实体）

- **color**: 颜色索引 (0-256, 256=随层)
- **lineweight**: 线宽 (-1=随层, -2=随块, -3=默认)

---

## 数据结构

### 参数对象结构

```typescript
interface Parameter {
  value: any;              // 参数当前值
  editable: boolean;       // 是否可编辑
  type: string;           // 参数类型
  description: string;    // 参数描述
  min?: number;           // 最小值（可选）
  max?: number;           // 最大值（可选）
}
```

### 参数类型

| 类型 | 说明 | 示例 |
|-----|------|------|
| `point` | 三维坐标 | `[1000.0, 2000.0, 0.0]` |
| `number` | 数值 | `50.0`, `256` |
| `string` | 文本（支持中文GBK） | `"桩号 K0+000"` |
| `boolean` | 布尔值 | `true`, `false` |
| `point_array` | 坐标数组 | `[[0,0,0], [100,100,0]]` |
| `array` | 普通数组 | `[1, 2, 3, 4]` |

---

## 使用示例

### 完整工作流程

#### 1. 上传并预览

```javascript
// 上传 DXF 并生成预览
const response = await fetch('/api/template/image/preview', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    template: {
      dxf_url: 'http://database.yuxindazhineng.com/bucket/road.dxf'
    }
  })
});

const { preview_url } = await response.json();
// 显示预览图
```

#### 2. 获取坐标范围

```javascript
// 获取 DXF 边界
const extentRes = await fetch('/api/template/image/extent', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    template: {
      dxf_url: 'http://database.yuxindazhineng.com/bucket/road.dxf'
    }
  })
});

const extent = await extentRes.json();
// { min_x, min_y, max_x, max_y }
```

#### 3. 点击图片查询实体

```javascript
// 用户点击图片
const handleImageClick = async (event) => {
  const rect = event.target.getBoundingClientRect();
  const clickX = event.clientX - rect.left;
  const clickY = event.clientY - rect.top;
  
  // 转换为 DXF 坐标
  const dxfX = extent.min_x + (clickX / imageWidth) * (extent.max_x - extent.min_x);
  const dxfY = extent.max_y - (clickY / imageHeight) * (extent.max_y - extent.min_y);
  
  // 查询实体
  const entityRes = await fetch('/api/template/image/entity-at', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      template: {
        dxf_url: 'http://database.yuxindazhineng.com/bucket/road.dxf'
      },
      x: dxfX,
      y: dxfY,
      tolerance: 500
    })
  });
  
  const { entities } = await entityRes.json();
  // 显示实体参数
};
```

#### 4. 修改参数并生成

```javascript
// 收集修改
const modifications = [
  {
    handle: "37A64",
    changes: {
      center: [65500.0, 6200.0, 0.0],
      radius: 2.0
    }
  }
];

// 生成新 DXF
const generateRes = await fetch('/api/template/image/generate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    template: {
      name: '测试道路',
      dxf_url: 'http://database.yuxindazhineng.com/bucket/road.dxf'
    },
    modifications
  })
});

const { dxf_url } = await generateRes.json();
// 下载新 DXF
```

---

## 工具脚本

### DXF 转换工具

#### 1. 转换为 R12 格式

```bash
python3 convert_to_r12.py
```

**功能**:
- 将任意版本 DXF 转换为 R12
- 处理颜色兼容性（0-255）
- 使用 GBK 编码
- 跳过不兼容实体（INSERT, LEADER）

**输入**: `/Users/czy/Desktop/测试道路平纵面，横断面.dxf`  
**输出**: `/Users/czy/Desktop/测试道路平纵面，横断面_R12.dxf`

#### 2. 生成带提示词的 R12 DXF

```bash
python3 create_r12_with_prompt.py
```

**功能**:
- 转换为 R12
- 在 HEADER 段添加标记
- 内嵌隐藏提示词 TEXT 实体

**输出**: `/Users/czy/Desktop/测试道路_R12带提示词.dxf`

#### 3. 生成 TXT 格式（提示词 + DXF）

```bash
python3 create_txt_with_dxf_and_prompt.py
```

**功能**:
- 提示词在顶部
- 完整 R12 DXF 数据在底部
- 可用文本编辑器查看

**输出**: `/Users/czy/Desktop/测试道路_R12数据和提示词.txt`

#### 4. 从 TXT 提取 DXF

```bash
python3 extract_dxf_from_txt.py
```

**功能**:
- 从 TXT 文件提取 DXF 部分
- 保存为标准 .dxf 文件
- 自动验证有效性

**输出**: `/Users/czy/Desktop/测试道路_从TXT提取.dxf`

#### 5. 生成纯提示词模板

```bash
python3 generate_prompt_only.py
```

**功能**:
- 分析 DXF 文件
- 生成详细的参数说明文档
- 包含示例和使用流程

**输出**: `/Users/czy/Desktop/测试道路_完整提示词模板.txt`

#### 6. 测试 DXF 实体

```bash
python3 test_dxf_entities.py
```

**功能**:
- 统计所有实体类型
- 显示样本数据
- 检查支持情况

---

## 错误处理

### 常见错误码

| 状态码 | 说明 | 解决方案 |
|-------|------|---------|
| 400 | 请求参数错误 | 检查 JSON 格式和必需字段 |
| 404 | DXF 文件未找到 | 确认 URL 正确且文件存在 |
| 500 | 服务器内部错误 | 查看后端日志 |

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

### 常见问题

#### 1. 中文乱码

**原因**: 编码不匹配  
**解决**: 
- 确保 DXF 使用 GBK (cp936) 编码
- R12 格式必须使用 GBK

#### 2. 实体未找到

**原因**: 容差太小或坐标转换错误  
**解决**:
- 增大 `tolerance` 参数（建议 500）
- 检查坐标转换逻辑

#### 3. 修改未生效

**原因**: 参数格式错误  
**解决**:
- 坐标必须是数组 `[x, y, z]`
- 数值不能是字符串
- 布尔值用 `true/false`

---

## 性能优化

### 大文件处理

- ✅ 按需加载实体（不加载全部到内存）
- ✅ 图像预览缓存
- ✅ 临时文件自动清理
- ✅ 异步处理

### 推荐配置

| 参数 | 推荐值 | 说明 |
|-----|-------|------|
| tolerance | 500 | 搜索容差 |
| 图片宽度 | 1920px | 预览图宽度 |
| 图片高度 | 1080px | 预览图高度 |

---

## 技术栈

- **后端**: FastAPI + Python 3.9+
- **DXF 处理**: ezdxf
- **渲染**: QGIS 4.0
- **存储**: MinIO
- **前端**: React + JavaScript

---

## 版本历史

### v1.0 (2026-05-28)

- ✅ 支持 10 种实体类型（覆盖率 100%）
- ✅ 图像预览和点选编辑
- ✅ R12 格式转换
- ✅ GBK 编码支持中文
- ✅ 颜色和线宽编辑
- ✅ 多段线、块引用、引线支持

---

## 联系方式

**项目路径**: `/Users/czy/Downloads/QGIS/dxf_render_service`  
**端口**: 8080 (后端), 3000 (前端)  
**MinIO**: `http://database.yuxindazhineng.com/`

---

## 附录

### A. 完整实体参数列表

详见 `/Users/czy/Desktop/测试道路_完整提示词模板.txt`

### B. 示例文件

- 测试文件: `/Users/czy/Desktop/测试道路平纵面，横断面.dxf`
- R12 转换: `/Users/czy/Desktop/测试道路_R12带提示词.dxf`
- 提示词模板: `/Users/czy/Desktop/测试道路_完整提示词模板.txt`

---

**文档版本**: 1.0  
**最后更新**: 2026-05-29
