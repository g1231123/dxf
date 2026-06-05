/**
 * DXF 编辑器组件
 * 
 * 功能：
 * 1. 加载并预览 DXF 文件
 * 2. 点击实体显示参数
 * 3. 修改参数并实时预览
 * 4. 生成新的 DXF 文件
 * 
 * 依赖：
 * - dxf-parser: DXF 文件解析
 * - three.js: 3D 渲染
 */

import React, { useState, useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import DxfParser from 'dxf-parser';

function DxfEditor({ templateId }) {
  const [dxfData, setDxfData] = useState(null);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [modifications, setModifications] = useState({});
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [manualLoad, setManualLoad] = useState(false); // 手动加载标志
  
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);
  const entityMeshesRef = useRef({});
  const animationIdRef = useRef(null);

  // 1. 加载 DXF 文件（只在点击加载按钮后执行）
  useEffect(() => {
    if (!templateId || !manualLoad) return;
    
    async function loadDxf() {
      setLoading(true);
      try {
        // 从后端获取 DXF 文件
        const response = await fetch(`/api/template/v2/file?id=${templateId}`);
        const dxfText = await response.text();
        
        // 解析 DXF
        const parser = new DxfParser();
        const dxf = parser.parseSync(dxfText);
        
        console.log('DXF 解析完成:', dxf);
        setDxfData(dxf);
        
        // 初始化 3D 场景
        initScene(dxf);
      } catch (error) {
        console.error('加载 DXF 失败:', error);
        alert('加载 DXF 失败: ' + error.message);
      } finally {
        setLoading(false);
      }
    }
    
    loadDxf();
    
    return () => {
      // 停止动画循环
      if (animationIdRef.current) {
        cancelAnimationFrame(animationIdRef.current);
      }
      
      // 清理 Three.js 资源
      if (rendererRef.current) {
        rendererRef.current.dispose();
      }
      
      // 清理场景
      if (sceneRef.current) {
        sceneRef.current.traverse((object) => {
          if (object.geometry) object.geometry.dispose();
          if (object.material) {
            if (Array.isArray(object.material)) {
              object.material.forEach(material => material.dispose());
            } else {
              object.material.dispose();
            }
          }
        });
      }
    };
  }, [templateId, manualLoad]);
  
  // 重置加载状态（切换模板时）
  useEffect(() => {
    setManualLoad(false);
    setDxfData(null);
    setModifications({});
  }, [templateId]);

  // 2. 初始化 Three.js 场景
  function initScene(dxf) {
    const container = containerRef.current;
    if (!container) return;
    
    // 创建场景
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f0f0);
    sceneRef.current = scene;
    
    // 创建相机
    const camera = new THREE.PerspectiveCamera(
      75,
      container.clientWidth / container.clientHeight,
      0.1,
      10000
    );
    camera.position.set(0, 0, 100);
    cameraRef.current = camera;
    
    // 创建渲染器
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;
    
    // 添加控制器
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controlsRef.current = controls;
    
    // 添加网格（根据场景大小动态调整）
    // 先不添加，等渲染完实体后根据实际大小添加
    
    // 渲染 DXF 实体
    renderDxfEntities(dxf, scene);
    
    // 自动调整相机位置以适应所有实体
    fitCameraToScene(scene, camera, controls);
    
    // 添加点击事件
    addClickHandler(renderer, camera, scene);
    
    // 动画循环
    function animate() {
      animationIdRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();
  }
  
  // 自动调整相机以适应场景
  function fitCameraToScene(scene, camera, controls) {
    const box = new THREE.Box3();
    
    // 计算场景中所有对象的包围盒
    scene.traverse((object) => {
      if (object.isMesh || object.isLine) {
        box.expandByObject(object);
      }
    });
    
    if (box.isEmpty()) {
      console.warn('场景为空');
      return;
    }
    
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    
    // 计算合适的相机距离
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
    cameraZ *= 1.5; // 留一些边距
    
    // 设置相机位置
    camera.position.set(center.x, center.y, center.z + cameraZ);
    camera.lookAt(center);
    
    // 设置控制器目标
    controls.target.copy(center);
    controls.update();
    
    console.log('场景范围:', { center, size, cameraZ });
  }

  // 3. 渲染 DXF 实体
  function renderDxfEntities(dxf, scene) {
    const entityMeshes = {};
    let renderedCount = 0;
    
    console.log(`开始渲染 ${dxf.entities.length} 个实体`);
    
    dxf.entities.forEach(entity => {
      let mesh = null;
      
      try {
        if (entity.type === 'LINE') {
          // 渲染直线
          if (entity.vertices && entity.vertices.length >= 2) {
            const points = [
              new THREE.Vector3(entity.vertices[0].x, entity.vertices[0].y, entity.vertices[0].z || 0),
              new THREE.Vector3(entity.vertices[1].x, entity.vertices[1].y, entity.vertices[1].z || 0)
            ];
            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            const material = new THREE.LineBasicMaterial({ 
              color: 0x000000,
              linewidth: 2
            });
            mesh = new THREE.Line(geometry, material);
          }
        }
        
        else if (entity.type === 'CIRCLE') {
          // 渲染圆
          const geometry = new THREE.CircleGeometry(entity.radius, 32);
          const material = new THREE.MeshBasicMaterial({ 
            color: 0x0000ff, 
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.5
          });
          mesh = new THREE.Mesh(geometry, material);
          mesh.position.set(entity.center.x, entity.center.y, entity.center.z || 0);
        }
        
        else if (entity.type === 'ARC') {
          // 渲染圆弧
          const curve = new THREE.EllipseCurve(
            entity.center.x, entity.center.y,
            entity.radius, entity.radius,
            entity.startAngle * Math.PI / 180,
            entity.endAngle * Math.PI / 180,
            false,
            0
          );
          const points = curve.getPoints(50);
          const geometry = new THREE.BufferGeometry().setFromPoints(points);
          const material = new THREE.LineBasicMaterial({ color: 0x000000 });
          mesh = new THREE.Line(geometry, material);
        }
        
        else if (entity.type === 'LWPOLYLINE' || entity.type === 'POLYLINE') {
          // 渲染多段线
          const points = entity.vertices.map(v => 
            new THREE.Vector3(v.x, v.y, v.z || 0)
          );
          const geometry = new THREE.BufferGeometry().setFromPoints(points);
          const material = new THREE.LineBasicMaterial({ color: 0x000000 });
          mesh = new THREE.Line(geometry, material);
        }
        
        else if (entity.type === 'TEXT' || entity.type === 'MTEXT') {
          // 渲染文字（简化版，使用 Sprite）
          const canvas = document.createElement('canvas');
          const context = canvas.getContext('2d');
          canvas.width = 256;
          canvas.height = 64;
          context.font = '24px Arial';
          context.fillStyle = 'black';
          context.fillText(entity.text || '', 10, 40);
          
          const texture = new THREE.CanvasTexture(canvas);
          const material = new THREE.SpriteMaterial({ map: texture });
          mesh = new THREE.Sprite(material);
          mesh.position.set(
            entity.position?.x || entity.startPoint?.x || 0,
            entity.position?.y || entity.startPoint?.y || 0,
            entity.position?.z || entity.startPoint?.z || 0
          );
          mesh.scale.set(entity.height || 10, (entity.height || 10) / 4, 1);
        }
        
        if (mesh) {
          mesh.userData = { 
            entity,
            handle: entity.handle,
            type: entity.type
          };
          scene.add(mesh);
          entityMeshes[entity.handle] = mesh;
          renderedCount++;
        }
      } catch (error) {
        console.warn(`渲染实体失败: ${entity.type}`, error);
      }
    });
    
    console.log(`成功渲染 ${renderedCount}/${dxf.entities.length} 个实体`);
    entityMeshesRef.current = entityMeshes;
  }

  // 4. 添加点击事件处理
  function addClickHandler(renderer, camera, scene) {
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    
    renderer.domElement.addEventListener('click', (event) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(scene.children, true);
      
      if (intersects.length > 0) {
        const object = intersects[0].object;
        if (object.userData.entity) {
          handleEntityClick(object.userData.entity);
        }
      }
    });
  }

  // 5. 处理实体点击
  function handleEntityClick(entity) {
    console.log('选中实体:', entity);
    setSelectedEntity(entity);
  }

  // 6. 修改参数
  function handleParamChange(handle, paramName, value) {
    setModifications(prev => ({
      ...prev,
      [handle]: {
        ...prev[handle],
        [paramName]: value
      }
    }));
    
    // 实时更新预览
    updateEntityPreview(handle, paramName, value);
  }

  // 7. 更新实体预览
  function updateEntityPreview(handle, paramName, value) {
    const mesh = entityMeshesRef.current[handle];
    if (!mesh) return;
    
    const entity = mesh.userData.entity;
    
    // 根据参数类型更新
    if (entity.type === 'LINE') {
      if (paramName === 'startX') {
        const points = mesh.geometry.attributes.position.array;
        points[0] = value;
        mesh.geometry.attributes.position.needsUpdate = true;
      }
      // ... 其他参数
    } else if (entity.type === 'TEXT') {
      if (paramName === 'text') {
        // 重新渲染文字
        // TODO: 更新 sprite 纹理
      }
    }
  }

  // 8. 生成新 DXF
  async function handleGenerate() {
    if (Object.keys(modifications).length === 0) {
      alert('没有修改任何参数');
      return;
    }
    
    setGenerating(true);
    try {
      // 构建修改数据
      const modArray = Object.entries(modifications).map(([handle, changes]) => {
        const entity = dxfData.entities.find(e => e.handle === handle);
        return {
          handle,
          type: entity?.type,
          changes
        };
      });
      
      // 发送到后端
      const formData = new FormData();
      formData.append('template_id', templateId);
      formData.append('modifications', JSON.stringify(modArray));
      
      const response = await fetch('/api/template/v2/generate', {
        method: 'POST',
        body: formData
      });
      
      const result = await response.json();
      
      if (result.code === 0) {
        alert(`生成成功！修改了 ${result.data.modified_count} 个实体`);
        // 下载文件
        window.location.href = result.data.file_url;
      } else {
        alert('生成失败: ' + result.message);
      }
    } catch (error) {
      console.error('生成失败:', error);
      alert('生成失败: ' + error.message);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="dxf-editor" style={{ display: 'flex', height: '100vh' }}>
      {/* 左侧：DXF 预览 */}
      <div style={{ flex: 1, position: 'relative' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        
        {/* 未加载时显示加载按钮 */}
        {!dxfData && !loading && (
          <div style={{ 
            position: 'absolute', 
            top: '50%', 
            left: '50%', 
            transform: 'translate(-50%, -50%)',
            textAlign: 'center'
          }}>
            <div style={{ fontSize: '48px', marginBottom: '20px' }}>📐</div>
            <button
              onClick={() => setManualLoad(true)}
              style={{
                padding: '15px 30px',
                fontSize: '16px',
                background: '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)'
              }}
            >
              点击加载 DXF 预览
            </button>
            <p style={{ marginTop: '15px', color: '#666', fontSize: '14px' }}>
              大文件可能需要较长时间解析
            </p>
          </div>
        )}
        
        {/* 加载中 */}
        {loading && (
          <div style={{ 
            position: 'absolute', 
            top: '50%', 
            left: '50%', 
            transform: 'translate(-50%, -50%)',
            background: 'white',
            padding: '20px',
            borderRadius: '8px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)'
          }}>
            <div style={{ marginBottom: '10px' }}>正在加载和解析 DXF...</div>
            <div style={{ fontSize: '12px', color: '#666' }}>请稍候</div>
          </div>
        )}
      </div>
      
      {/* 右侧：参数编辑面板 */}
      <div style={{ width: '300px', padding: '20px', overflowY: 'auto', borderLeft: '1px solid #ccc' }}>
        <h2>DXF 编辑器</h2>
        
        {selectedEntity ? (
          <EntityEditPanel
            entity={selectedEntity}
            modifications={modifications[selectedEntity.handle] || {}}
            onChange={(param, value) => handleParamChange(selectedEntity.handle, param, value)}
          />
        ) : (
          <p>点击实体以编辑参数</p>
        )}
        
        <div style={{ marginTop: '20px' }}>
          <button 
            onClick={handleGenerate}
            disabled={generating || Object.keys(modifications).length === 0}
            style={{ 
              width: '100%', 
              padding: '10px', 
              marginBottom: '10px',
              background: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            {generating ? '生成中...' : `生成 DXF (${Object.keys(modifications).length} 处修改)`}
          </button>
          
          <button 
            onClick={() => setModifications({})}
            disabled={Object.keys(modifications).length === 0}
            style={{ 
              width: '100%', 
              padding: '10px',
              background: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            重置所有修改
          </button>
        </div>
      </div>
    </div>
  );
}

// 实体编辑面板
function EntityEditPanel({ entity, modifications, onChange }) {
  const getValue = (key, defaultValue) => {
    return modifications[key] !== undefined ? modifications[key] : defaultValue;
  };
  
  if (entity.type === 'LINE') {
    return (
      <div>
        <h3>直线</h3>
        <p>句柄: {entity.handle}</p>
        
        <label>
          起点 X:
          <input
            type="number"
            step="0.1"
            value={getValue('startX', entity.vertices[0].x)}
            onChange={e => onChange('startX', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
        
        <label>
          起点 Y:
          <input
            type="number"
            step="0.1"
            value={getValue('startY', entity.vertices[0].y)}
            onChange={e => onChange('startY', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
        
        <label>
          终点 X:
          <input
            type="number"
            step="0.1"
            value={getValue('endX', entity.vertices[1].x)}
            onChange={e => onChange('endX', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
        
        <label>
          终点 Y:
          <input
            type="number"
            step="0.1"
            value={getValue('endY', entity.vertices[1].y)}
            onChange={e => onChange('endY', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
      </div>
    );
  }
  
  if (entity.type === 'CIRCLE') {
    return (
      <div>
        <h3>圆</h3>
        <p>句柄: {entity.handle}</p>
        
        <label>
          圆心 X:
          <input
            type="number"
            step="0.1"
            value={getValue('centerX', entity.center.x)}
            onChange={e => onChange('centerX', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
        
        <label>
          圆心 Y:
          <input
            type="number"
            step="0.1"
            value={getValue('centerY', entity.center.y)}
            onChange={e => onChange('centerY', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
        
        <label>
          半径:
          <input
            type="number"
            step="0.1"
            min="0.1"
            value={getValue('radius', entity.radius)}
            onChange={e => onChange('radius', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
      </div>
    );
  }
  
  if (entity.type === 'TEXT' || entity.type === 'MTEXT') {
    return (
      <div>
        <h3>文字</h3>
        <p>句柄: {entity.handle}</p>
        
        <label>
          文字内容:
          <input
            type="text"
            value={getValue('text', entity.text)}
            onChange={e => onChange('text', e.target.value)}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
        
        <label>
          字高:
          <input
            type="number"
            step="0.1"
            min="0.1"
            value={getValue('height', entity.height)}
            onChange={e => onChange('height', parseFloat(e.target.value))}
            style={{ width: '100%', marginBottom: '10px' }}
          />
        </label>
      </div>
    );
  }
  
  return (
    <div>
      <h3>{entity.type}</h3>
      <p>句柄: {entity.handle}</p>
      <p>暂不支持编辑此类型实体</p>
    </div>
  );
}

export default DxfEditor;
