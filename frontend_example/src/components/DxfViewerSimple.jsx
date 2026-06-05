/**
 * 简化的 DXF 查看器
 * 使用 three-dxf-loader 直接加载和渲染 DXF 文件
 */
import React, { useState, useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { DXFLoader } from 'three-dxf-loader';

function DxfViewerSimple({ templateId }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [manualLoad, setManualLoad] = useState(false);
  const [entityCount, setEntityCount] = useState(0);
  
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const animationIdRef = useRef(null);

  useEffect(() => {
    if (!templateId || !manualLoad) return;
    
    async function loadDxf() {
      setLoading(true);
      setError(null);
      
      try {
        // 获取 DXF 文件 URL
        const fileUrl = `/api/template/v2/file?id=${templateId}`;
        
        // 初始化场景
        const container = containerRef.current;
        if (!container) return;
        
        // 创建场景
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf5f5f5);
        sceneRef.current = scene;
        
        // 创建相机
        const camera = new THREE.PerspectiveCamera(
          45,
          container.clientWidth / container.clientHeight,
          1,
          100000
        );
        camera.position.set(0, 0, 1000);
        
        // 创建渲染器
        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        container.innerHTML = ''; // 清空容器
        container.appendChild(renderer.domElement);
        rendererRef.current = renderer;
        
        // 添加控制器
        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        
        // 添加光源
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);
        
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.4);
        directionalLight.position.set(1, 1, 1);
        scene.add(directionalLight);
        
        // 使用 DXFLoader 加载 DXF 文件
        const loader = new DXFLoader();
        
        console.log('开始加载 DXF:', fileUrl);
        
        loader.load(
          fileUrl,
          (dxf) => {
            console.log('DXF 加载成功:', dxf);
            
            // 添加 DXF 对象到场景
            scene.add(dxf);
            
            // 计算包围盒
            const box = new THREE.Box3().setFromObject(dxf);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            
            console.log('DXF 范围:', { center, size });
            
            // 调整相机位置
            const maxDim = Math.max(size.x, size.y, size.z);
            const fov = camera.fov * (Math.PI / 180);
            let cameraZ = Math.abs(maxDim / Math.tan(fov / 2));
            cameraZ *= 1.5;
            
            camera.position.set(center.x, center.y, center.z + cameraZ);
            camera.lookAt(center);
            controls.target.copy(center);
            controls.update();
            
            // 统计实体数量
            let count = 0;
            dxf.traverse((child) => {
              if (child.isMesh || child.isLine) {
                count++;
              }
            });
            setEntityCount(count);
            
            setLoading(false);
          },
          (progress) => {
            console.log('加载进度:', (progress.loaded / progress.total * 100).toFixed(2) + '%');
          },
          (err) => {
            console.error('加载失败:', err);
            setError('加载 DXF 失败: ' + err.message);
            setLoading(false);
          }
        );
        
        // 动画循环
        function animate() {
          animationIdRef.current = requestAnimationFrame(animate);
          controls.update();
          renderer.render(scene, camera);
        }
        animate();
        
      } catch (err) {
        console.error('初始化失败:', err);
        setError('初始化失败: ' + err.message);
        setLoading(false);
      }
    }
    
    loadDxf();
    
    return () => {
      // 清理
      if (animationIdRef.current) {
        cancelAnimationFrame(animationIdRef.current);
      }
      if (rendererRef.current) {
        rendererRef.current.dispose();
      }
    };
  }, [templateId, manualLoad]);
  
  // 切换模板时重置
  useEffect(() => {
    setManualLoad(false);
    setEntityCount(0);
    setError(null);
  }, [templateId]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      
      {/* 未加载时显示按钮 */}
      {!manualLoad && !loading && (
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
            使用 three-dxf-loader 直接渲染
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
          boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
          textAlign: 'center'
        }}>
          <div style={{ marginBottom: '10px' }}>正在加载 DXF...</div>
          <div style={{ fontSize: '12px', color: '#666' }}>请稍候</div>
        </div>
      )}
      
      {/* 错误提示 */}
      {error && (
        <div style={{
          position: 'absolute',
          top: '20px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#f8d7da',
          color: '#721c24',
          padding: '15px',
          borderRadius: '8px',
          maxWidth: '80%'
        }}>
          {error}
        </div>
      )}
      
      {/* 实体数量显示 */}
      {entityCount > 0 && (
        <div style={{
          position: 'absolute',
          top: '10px',
          right: '10px',
          background: 'rgba(255,255,255,0.9)',
          padding: '10px',
          borderRadius: '4px',
          fontSize: '12px'
        }}>
          实体数量: {entityCount}
        </div>
      )}
    </div>
  );
}

export default DxfViewerSimple;
