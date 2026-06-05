import React, { useState, useEffect } from 'react';
// import DxfParamEditor from './components/DxfParamEditor';
import DxfImageEditor from './components/DxfImageEditor';
import UploadModal from './components/UploadModal';

function App() {
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showUploadModal, setShowUploadModal] = useState(false);

  // 加载模板列表
  useEffect(() => {
    async function loadTemplates() {
      try {
        const response = await fetch('/api/template/list');
        const data = await response.json();
        if (data.code === 0) {
          setTemplates(data.data.records);
          // 自动选择第一个模板
          if (data.data.records.length > 0) {
            setSelectedTemplate(data.data.records[0].id);
          }
        }
      } catch (error) {
        console.error('加载模板列表失败:', error);
      } finally {
        setLoading(false);
      }
    }
    
    loadTemplates();
  }, []);

  // 上传成功后刷新列表
  const handleUploadSuccess = (newTemplate) => {
    setTemplates(prev => [newTemplate, ...prev]);
    setSelectedTemplate(newTemplate.id);
  };

  return (
    <div style={{ display: 'flex', height: '100vh', flexDirection: 'column' }}>
      {/* 顶部标题栏 */}
      <div style={{ 
        padding: '15px 20px', 
        background: '#2c3e50', 
        color: 'white',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <h1 style={{ margin: 0, fontSize: '20px' }}>DXF 模板编辑器 - 前端驱动方案</h1>
        <p style={{ margin: '5px 0 0 0', fontSize: '12px', opacity: 0.8 }}>
          点击 DXF 实体即可编辑参数，无需加载所有数据
        </p>
      </div>

      {/* 主体区域 */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 左侧：模板列表 */}
        <div style={{ 
          width: '250px', 
          borderRight: '1px solid #ddd', 
          overflowY: 'auto',
          background: '#f8f9fa'
        }}>
          <div style={{ padding: '15px', borderBottom: '1px solid #ddd', background: 'white' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 style={{ margin: 0, fontSize: '16px' }}>模板列表</h3>
              <button
                onClick={() => setShowUploadModal(true)}
                style={{
                  padding: '6px 12px',
                  background: '#28a745',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: 'bold'
                }}
              >
                + 上传
              </button>
            </div>
            <p style={{ margin: '5px 0 0 0', fontSize: '12px', color: '#666' }}>
              共 {templates.length} 个模板
            </p>
          </div>
          
          {loading ? (
            <div style={{ padding: '20px', textAlign: 'center', color: '#666' }}>
              加载中...
            </div>
          ) : templates.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: '#666' }}>
              暂无模板
            </div>
          ) : (
            <div>
              {templates.map(template => (
                <div
                  key={template.id}
                  onClick={() => setSelectedTemplate(template.id)}
                  style={{
                    padding: '12px 15px',
                    cursor: 'pointer',
                    background: selectedTemplate === template.id ? '#007bff' : 'white',
                    color: selectedTemplate === template.id ? 'white' : '#333',
                    borderBottom: '1px solid #eee',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedTemplate !== template.id) {
                      e.target.style.background = '#f0f0f0';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedTemplate !== template.id) {
                      e.target.style.background = 'white';
                    }
                  }}
                >
                  <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>
                    {template.name}
                  </div>
                  <div style={{ fontSize: '11px', opacity: 0.8 }}>
                    {template.entity_count} 个实体
                    {template.is_official === 1 && (
                      <span style={{ 
                        marginLeft: '8px', 
                        padding: '2px 6px', 
                        background: selectedTemplate === template.id ? 'rgba(255,255,255,0.2)' : '#28a745',
                        color: selectedTemplate === template.id ? 'white' : 'white',
                        borderRadius: '3px',
                        fontSize: '10px'
                      }}>
                        官方
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* 右侧：图片编辑器 */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          {selectedTemplate ? (
            <DxfImageEditor key={selectedTemplate} templateId={selectedTemplate} />
          ) : (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              height: '100%',
              color: '#999'
            }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '48px', marginBottom: '10px' }}>📐</div>
                <div>请选择一个模板开始编辑</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 上传模态框 */}
      {showUploadModal && (
        <UploadModal
          onClose={() => setShowUploadModal(false)}
          onUploadSuccess={handleUploadSuccess}
        />
      )}
    </div>
  );
}

export default App;
