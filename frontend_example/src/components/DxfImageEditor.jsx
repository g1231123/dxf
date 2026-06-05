/**
 * DXF 图片点击编辑器
 * 1. 显示 DXF 预览图
 * 2. 点击图片查找实体
 * 3. 编辑参数并生成新 DXF
 */
import React, { useState, useEffect, useRef } from 'react';

function DxfImageEditor({ templateId }) {
  const [template, setTemplate] = useState(null);
  const [imageUrl, setImageUrl] = useState('');
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [dxfExtent, setDxfExtent] = useState(null);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [entities, setEntities] = useState([]);
  const [modifications, setModifications] = useState({});
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [clickPoint, setClickPoint] = useState(null);
  
  const imageRef = useRef(null);
  const canvasRef = useRef(null);

  // 加载模板信息和 DXF 范围
  useEffect(() => {
    async function loadTemplate() {
      try {
        const response = await fetch(`/api/template/detail?id=${templateId}`);
        const data = await response.json();
        if (data.code === 0) {
          setTemplate(data.data);
          // 生成预览图 URL
          setImageUrl(`/api/template/image/preview?template_id=${templateId}&width=1200`);
        }
        
        // 获取 DXF 范围
        const extentResponse = await fetch(`/api/template/image/extent?template_id=${templateId}`);
        const extentData = await extentResponse.json();
        if (extentData.code === 0) {
          setDxfExtent(extentData.data);
          console.log('DXF 范围:', extentData.data);
        }
      } catch (error) {
        console.error('加载模板失败:', error);
      }
    }
    loadTemplate();
  }, [templateId]);

  // 图片加载完成
  const handleImageLoad = (e) => {
    const img = e.target;
    setImageSize({ width: img.naturalWidth, height: img.naturalHeight });
  };

  // 点击图片
  const handleImageClick = async (e) => {
    if (!imageRef.current || !dxfExtent) return;
    
    const rect = imageRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    
    // 转换为 DXF 图纸坐标
    // 图片坐标 -> DXF 坐标
    const imgWidth = rect.width;
    const imgHeight = rect.height;
    
    // DXF 坐标系：Y 轴向上，图片坐标系：Y 轴向下
    const dxfX = dxfExtent.min[0] + (clickX / imgWidth) * dxfExtent.width;
    const dxfY = dxfExtent.max[1] - (clickY / imgHeight) * dxfExtent.height;
    
    console.log('点击位置:', { clickX, clickY, dxfX, dxfY });
    
    setClickPoint({ x: clickX, y: clickY });
    
    // 查找实体
    setLoading(true);
    try {
      const response = await fetch(
        `/api/template/image/entity-at?template_id=${templateId}&x=${dxfX}&y=${dxfY}&tolerance=500`
      );
      const data = await response.json();
      if (data.code === 0) {
        setEntities(data.data.entities);
        if (data.data.entities.length > 0) {
          setSelectedEntity(data.data.entities[0]);
        } else {
          alert('未找到实体，请点击线条或文字附近');
        }
      }
    } catch (error) {
      console.error('查找实体失败:', error);
      alert('查找实体失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 修改参数
  const handleParamChange = (key, value) => {
    if (!selectedEntity) return;
    
    const newMods = { ...modifications };
    if (!newMods[selectedEntity.handle]) {
      newMods[selectedEntity.handle] = {};
    }
    
    try {
      // 尝试解析 JSON（用于数组和数字）
      const parsed = JSON.parse(value);
      newMods[selectedEntity.handle][key] = parsed;
    } catch {
      // 如果解析失败，作为字符串
      newMods[selectedEntity.handle][key] = value;
    }
    
    setModifications(newMods);
  };

  // 生成新 DXF
  const handleGenerate = async () => {
    if (Object.keys(modifications).length === 0) {
      alert('没有修改任何参数');
      return;
    }

    setGenerating(true);
    try {
      const formData = new FormData();
      formData.append('template_id', templateId);
      formData.append('modifications', JSON.stringify(
        Object.entries(modifications).map(([handle, changes]) => ({
          handle,
          changes
        }))
      ));

      const response = await fetch('/api/template/image/generate', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();
      if (result.code === 0) {
        alert(`生成成功！修改了 ${result.data.modified_count} 个实体`);
        window.location.href = result.data.file_url;
      } else {
        alert('生成失败: ' + result.message);
      }
    } catch (error) {
      alert('生成失败: ' + error.message);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* 顶部信息栏 */}
      <div style={{ 
        padding: '20px',
        borderBottom: '1px solid #ddd',
        background: '#f8f9fa'
      }}>
        <h2 style={{ margin: '0 0 10px 0' }}>{template?.name || '加载中...'}</h2>
        {template && (
          <div style={{ fontSize: '14px', color: '#666' }}>
            点击图片上的实体进行编辑
          </div>
        )}
      </div>

      {/* 主体区域 */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* 左侧：图片预览 */}
        <div style={{ 
          flex: 1, 
          overflow: 'auto', 
          padding: '20px',
          background: '#f5f5f5',
          position: 'relative'
        }}>
          {imageUrl ? (
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <img
                ref={imageRef}
                src={imageUrl}
                alt="DXF Preview"
                onLoad={handleImageLoad}
                onClick={handleImageClick}
                style={{
                  maxWidth: '100%',
                  cursor: 'crosshair',
                  border: '1px solid #ddd',
                  background: 'white'
                }}
              />
              
              {/* 点击标记 */}
              {clickPoint && (
                <div style={{
                  position: 'absolute',
                  left: clickPoint.x - 5,
                  top: clickPoint.y - 5,
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: 'red',
                  border: '2px solid white',
                  pointerEvents: 'none'
                }} />
              )}
              
              {loading && (
                <div style={{
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  background: 'rgba(0,0,0,0.7)',
                  color: 'white',
                  padding: '10px 20px',
                  borderRadius: '4px'
                }}>
                  查找实体中...
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
              <div style={{ fontSize: '48px', marginBottom: '20px' }}>🖼️</div>
              <div>正在生成预览图...</div>
            </div>
          )}
        </div>

        {/* 右侧：参数编辑 */}
        <div style={{ 
          width: '350px', 
          borderLeft: '1px solid #ddd',
          overflow: 'auto',
          background: 'white'
        }}>
          {selectedEntity ? (
            <div style={{ padding: '20px' }}>
              <h3 style={{ marginTop: 0 }}>编辑实体</h3>
              
              <div style={{ 
                marginBottom: '20px',
                padding: '10px',
                background: '#f8f9fa',
                borderRadius: '4px'
              }}>
                <div><strong>类型:</strong> {selectedEntity.type}</div>
                <div><strong>图层:</strong> {selectedEntity.layer}</div>
                <div><strong>句柄:</strong> {selectedEntity.handle}</div>
                <div><strong>距离:</strong> {selectedEntity.distance.toFixed(2)}</div>
              </div>

              {/* 参数编辑 */}
              <div>
                <h4>参数</h4>
                {Object.entries(selectedEntity.params).map(([key, param]) => {
                  const value = param.value;
                  const editable = param.editable !== false;
                  const description = param.description || key;
                  
                  return (
                    <div key={key} style={{ marginBottom: '15px' }}>
                      <label style={{ 
                        display: 'block', 
                        marginBottom: '5px', 
                        fontWeight: 'bold',
                        color: editable ? '#000' : '#999'
                      }}>
                        {description}:
                        {!editable && <span style={{ fontSize: '11px', marginLeft: '5px' }}>(只读)</span>}
                      </label>
                      <input
                        type="text"
                        defaultValue={Array.isArray(value) ? JSON.stringify(value) : value}
                        onChange={(e) => handleParamChange(key, e.target.value)}
                        disabled={!editable}
                        style={{
                          width: '100%',
                          padding: '8px',
                          border: '1px solid #ddd',
                          borderRadius: '4px',
                          background: editable ? 'white' : '#f5f5f5',
                          cursor: editable ? 'text' : 'not-allowed'
                        }}
                      />
                      <div style={{ fontSize: '11px', color: '#666', marginTop: '3px' }}>
                        当前值: {Array.isArray(value) ? JSON.stringify(value) : value}
                        {param.min !== undefined && ` (最小: ${param.min})`}
                        {param.max !== undefined && ` (最大: ${param.max})`}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* 其他找到的实体 */}
              {entities.length > 1 && (
                <div style={{ marginTop: '20px' }}>
                  <h4>附近的其他实体 ({entities.length - 1})</h4>
                  {entities.slice(1, 6).map((entity, idx) => (
                    <div
                      key={entity.handle}
                      onClick={() => setSelectedEntity(entity)}
                      style={{
                        padding: '10px',
                        marginBottom: '5px',
                        background: '#f8f9fa',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      {entity.type} - {entity.layer} (距离: {entity.distance.toFixed(1)})
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div style={{ 
              padding: '40px',
              textAlign: 'center',
              color: '#999'
            }}>
              <div style={{ fontSize: '48px', marginBottom: '20px' }}>👆</div>
              <div>点击图片上的实体</div>
              <div style={{ fontSize: '12px', marginTop: '10px' }}>
                点击后会自动查找附近的实体
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 底部操作栏 */}
      {Object.keys(modifications).length > 0 && (
        <div style={{ 
          padding: '20px',
          borderTop: '1px solid #ddd',
          background: '#f8f9fa',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div>
            已修改 {Object.keys(modifications).length} 个实体
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={() => setModifications({})}
              style={{
                padding: '10px 20px',
                background: '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              重置
            </button>
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{
                padding: '10px 20px',
                background: generating ? '#ccc' : '#28a745',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: generating ? 'not-allowed' : 'pointer'
              }}
            >
              {generating ? '生成中...' : '生成 DXF'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default DxfImageEditor;
