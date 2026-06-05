# Windows 部署指南 - AutoCAD COM 版本

## 一、准备工作

### 需要的环境
- Windows 10/11 (64位)
- AutoCAD 2018/2019/2020/2021/2022/2023/2024/2025 任意版本
- Python 3.9+ (64位)
- 建议 8GB+ 内存

### 安装 Python
1. 下载 Python: https://python.org/downloads
2. 安装时勾选 **"Add Python to PATH"**
3. 验证安装:
   ```cmd
   python --version
   pip --version
   ```

## 二、安装依赖

```cmd
pip install pyautocad pywin32 ezdxf fastapi uvicorn websockets python-multipart
```

## 三、启动 AutoCAD

1. 打开 AutoCAD 软件
2. 新建一个空白图纸
3. 保持 AutoCAD **前台运行**（不要最小化）

## 四、部署服务端代码

### 1. 复制代码到 Windows 电脑
将整个 `dxf_render_service` 文件夹复制到 Windows，例如:
```
C:\cad_service\
```

### 2. 修改配置（可选）
编辑 `ws_server.py`，确保配置正确:
```python
# Windows 路径示例
QGIS_PREFIX = r"C:\Program Files\QGIS 3.32\apps\qgis"  # 如果有安装QGIS
# 或者只使用 ezdxf/pyautocad 不需要 QGIS
```

### 3. 启动服务端
```cmd
cd C:\cad_service
python server.py
```

看到以下日志表示成功:
```
INFO:     Started server process [xxxx]
INFO:     Uvicorn running on http://0.0.0.0:8080
Using AutoCAD COM engine for AI drawing  <-- 检测到 AutoCAD
```

## 五、测试连接

### 1. 打开测试页面
在浏览器打开:
```
http://localhost:8080/test_autocad_windows.html
```

### 2. 点击"🔗 连接 AutoCAD"

### 3. 绘制图形测试
- 选择"⭕ 圆"
- 设置参数: cx=100, cy=100, r=50
- 名称: "客厅"
- 点击"🎨 绘制到 AutoCAD"

### 4. 查看结果
- AutoCAD 中应该立即出现圆和文字
- 页面显示"✅ 绘制成功"

## 六、常见问题

### Q1: 提示 "AutoCAD COM not available"
**解决:**
- 确保 AutoCAD 已启动
- 以管理员身份运行 CMD: `右键 → 以管理员身份运行`
- 重新运行 `python server.py`

### Q2: 文字显示为乱码或?
**解决:**
- 在 AutoCAD 中设置字体：
  - 命令行输入 `STYLE`
  - 选择 `Standard` 样式
  - 字体名改为 `宋体` 或 `SimSun`

### Q3: 绘制很慢
**解决:**
- 确保 AutoCAD 窗口可见（不要最小化）
- 关闭 AutoCAD 的图形加速：
  - 命令: `GRAPHICSCONFIG`
  - 关闭硬件加速

### Q4: 中文显示方框
**解决:**
```python
# 在 ws_server.py 中添加文字前设置字体
text.StyleName = "Standard"  # 确保使用支持中文的字体样式
```

## 七、部署到生产环境

### 使用 Windows 服务（后台运行）

1. 安装 nssm:
   ```cmd
   choco install nssm
   # 或者手动下载 https://nssm.cc/download
   ```

2. 创建服务:
   ```cmd
   nssm install CADService
   # Path: C:\Python39\python.exe
   # Arguments: C:\cad_service\server.py
   # 工作目录: C:\cad_service
   ```

3. 启动服务:
   ```cmd
   nssm start CADService
   ```

### 防火墙设置

允许 8080 端口:
```cmd
netsh advfirewall firewall add rule name="CAD Service" dir=in action=allow protocol=TCP localport=8080
```

## 八、文件清单

部署时需要复制这些文件到 Windows:
```
dxf_render_service/
├── server.py              # 主入口
├── ws_server.py           # WebSocket 处理（含 pyautocad 支持）
├── API.md                 # API 文档
├── WINDOWS_DEPLOY.md      # 本文件
└── test_autocad_windows.html  # 测试页面
```

## 九、验证安装

在 Python 中测试 pyautocad:
```python
python -c "from pyautocad import Autocad; a = Autocad(); print(a.doc.Name)"
```

输出类似 `Drawing1.dwg` 表示成功。

## 十、联系支持

遇到问题:
1. 检查 AutoCAD 是否运行
2. 查看服务端日志
3. 确认 pyautocad 安装: `pip list | findstr pyautocad`
