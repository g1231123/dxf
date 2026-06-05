/**
 * DXF 参数编辑器
 * 不渲染 DXF，直接显示可编辑参数列表
 */
import React, { useState, useEffect } from 'react';

function DxfParamEditor({ templateId }) {
  const [template, setTemplate] = useState(null);
  const [layers, setLayers] = useState([]);
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingLayers, setLoadingLayers] = useState(false);
  const [modifications, setModifications] = useState({});
  const [generating, setGenerating] = useState(false);
  
  const [selectedLayer, setSelectedLayer] = useState('');
  const [selectedType, setSelectedType] = useState('');
  const [limit] = useState(100);

  // 加载模板信息
  useEffect(() => {
    async function loadTemplate() {
      try {
        const response = await fetch(`/api/template/detail?id=${templateId}`);
        const data = await response.json();
        if (data.code === 0) {
          setTemplate(data.data);
        }
      } catch (error) {
        console.error('加载模板失败:', error);
      }
    }
    loadTemplate();
  }, [templateId]);

  // 加载图层列表
  useEffect(() => {
    async function loadLayers() {
      if (!template) return;
      
      setLoadingLayers(true);
      try {
        const response = await fetch(`/api/template/ondemand/layers?template_id=${templateId}`);
        const data = await response.json();
        if (data.code === 0) {
          setLayers(data.data.layers || []);
        }
      } catch (error) {
        console.error('加载图层失败:', error);
      } finally {
        setLoadingLayers(false);
      }
    }
    
    loadLayers();
  }, [templateId, template]);

  // 加载实体（按需）
  const loadEntities = async () => {
    if (!selectedLayer && !selectedType) {
      alert('请先选择图层或实体类型');
      return;
    }
    
    setLoading(true);
    try {
      const params = new URLSearchParams({
        template_id: templateId,
        limit: limit.toString()
      });
      if (selectedLayer) params.append('layer', selectedLayer);
      if (selectedType) params.append('entity_type', selectedType);
      
      const response = await fetch(`/api/template/ondemand/entities?${params}`);
      const data = await response.json();
      if (data.code === 0) {
        setEntities(data.data.entities || []);
      }
    } catch (error) {
      console.error('加载实体失败:', error);
      alert('加载失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 修改参数
  const handleParamChange = (paramId, newValue) => {
    setModifications(prev => ({
      ...prev,
      [paramId]: newValue
    }));
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

      const response = await fetch('/api/template/ondemand/generate', {
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

  if (!template) {
    return <div style={{ padding: '20px' }}>加载中...</div>;
  }

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
            {template.entity_count} 个实体 | {layers.length} 个图层
          </div>
        )}
      </div>

      {/* 选择器和加载按钮 */}
      <div style={{ padding: '20px', borderBottom: '1px solid #ddd' }}>
        <div style={{ marginBottom: '15px' }}>
          <strong>按需加载实体参数：</strong>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <select 
            value={selectedLayer}
            onChange={(e) => setSelectedLayer(e.target.value)}
            style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minWidth: '150px' }}
            disabled={loadingLayers}
          >
            <option value="">选择图层</option>
            {layers.map(layer => (
              <option key={layer.name} value={layer.name}>
                {layer.name} {layer.description ? `- ${layer.description}` : ''}
              </option>
            ))}
          </select>
          
          <span style={{ color: '#666' }}>或</span>
          
          <input
            type="text"
            placeholder="输入图层名"
            value={selectedLayer}
            onChange={(e) => setSelectedLayer(e.target.value)}
            style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minWidth: '120px' }}
          />

          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minWidth: '120px' }}
          >
            <option value="">选择类型</option>
            <option value="LINE">直线</option>
            <option value="CIRCLE">圆</option>
            <option value="ARC">圆弧</option>
            <option value="TEXT">文字</option>
            <option value="MTEXT">多行文字</option>
          </select>

          <button
            onClick={loadEntities}
            disabled={loading || (!selectedLayer && !selectedType)}
            style={{
              padding: '8px 20px',
              background: (!selectedLayer && !selectedType) ? '#ccc' : '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: (!selectedLayer && !selectedType) ? 'not-allowed' : 'pointer'
            }}
          >
            {loading ? '加载中...' : `加载实体 (最多${limit}个)`}
          </button>
        </div>
      </div>

      {/* 实体列表 */}
      <div style={{ flex: 1, overflow: 'auto', padding: '20px' }}>
        {entities.length > 0 ? (
          <div>
            <div style={{ marginBottom: '15px', color: '#666' }}>
              已加载 {entities.length} 个实体
            </div>
            {entities.map(entity => (
              <div key={entity.handle} style={{ 
                marginBottom: '20px',
                padding: '15px',
                border: '1px solid #ddd',
                borderRadius: '8px',
                background: '#f8f9fa'
              }}>
                <div style={{ marginBottom: '10px', fontWeight: 'bold' }}>
                  {entity.type} - {entity.layer} (句柄: {entity.handle})
                </div>
                {Object.entries(entity.params).map(([key, value]) => (
                  <div key={key} style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label style={{ minWidth: '100px', fontWeight: 'bold' }}>{key}:</label>
                    <input
                      type="text"
                      defaultValue={Array.isArray(value) ? JSON.stringify(value) : value}
                      onChange={(e) => {
                        const newMods = { ...modifications };
                        if (!newMods[entity.handle]) newMods[entity.handle] = {};
                        try {
                          newMods[entity.handle][key] = JSON.parse(e.target.value);
                        } catch {
                          newMods[entity.handle][key] = e.target.value;
                        }
                        setModifications(newMods);
                      }}
                      style={{ flex: 1, padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    />
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
            <div style={{ fontSize: '48px', marginBottom: '20px' }}>📋</div>
            <div>选择图层或类型，然后点击"加载实体"</div>
          </div>
        )}
      </div>

      {/* 底部操作栏 */}
      {entities.length > 0 && (
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
              disabled={Object.keys(modifications).length === 0}
              style={{
                padding: '10px 20px',
                background: '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: Object.keys(modifications).length === 0 ? 'not-allowed' : 'pointer',
                opacity: Object.keys(modifications).length === 0 ? 0.5 : 1
              }}
            >
              重置
            </button>
            <button
              onClick={handleGenerate}
              disabled={generating || Object.keys(modifications).length === 0}
              style={{
                padding: '10px 20px',
                background: '#28a745',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: (generating || Object.keys(modifications).length === 0) ? 'not-allowed' : 'pointer',
                opacity: (generating || Object.keys(modifications).length === 0) ? 0.5 : 1
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

export default DxfParamEditor;
