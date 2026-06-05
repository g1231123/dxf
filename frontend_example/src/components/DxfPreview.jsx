/**
 * DXF 预览组件 - 轻量级版本
 * 只显示基本信息和下载链接，不在前端渲染大文件
 */
import React, { useState, useEffect } from 'react';

function DxfPreview({ templateId }) {
  const [template, setTemplate] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadTemplate() {
      try {
        const response = await fetch(`/api/template/detail?id=${templateId}`);
        const data = await response.json();
        if (data.code === 0) {
          setTemplate(data.data);
        }
      } catch (error) {
        console.error('加载模板信息失败:', error);
      } finally {
        setLoading(false);
      }
    }
    
    loadTemplate();
  }, [templateId]);

  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        height: '100%'
      }}>
        加载中...
      </div>
    );
  }

  if (!template) {
    return (
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        height: '100%'
      }}>
        模板不存在
      </div>
    );
  }

  return (
    <div style={{ 
      padding: '40px',
      maxWidth: '800px',
      margin: '0 auto'
    }}>
      <h2 style={{ marginBottom: '30px' }}>{template.name}</h2>
      
      {/* 基本信息 */}
      <div style={{ 
        background: '#f8f9fa',
        padding: '20px',
        borderRadius: '8px',
        marginBottom: '20px'
      }}>
        <h3 style={{ marginBottom: '15px' }}>基本信息</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '10px' }}>
          <div style={{ fontWeight: 'bold' }}>文件名:</div>
          <div>{template.original_filename}</div>
          
          <div style={{ fontWeight: 'bold' }}>DXF 版本:</div>
          <div>{template.dxf_version}</div>
          
          <div style={{ fontWeight: 'bold' }}>图层数量:</div>
          <div>{template.layer_count}</div>
          
          <div style={{ fontWeight: 'bold' }}>块数量:</div>
          <div>{template.block_count}</div>
          
          <div style={{ fontWeight: 'bold' }}>实体数量:</div>
          <div>{template.entity_count}</div>
          
          <div style={{ fontWeight: 'bold' }}>创建时间:</div>
          <div>{template.created_at}</div>
        </div>
      </div>

      {/* 范围信息 */}
      {template.extent_min_x && (
        <div style={{ 
          background: '#f8f9fa',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          <h3 style={{ marginBottom: '15px' }}>图纸范围</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '10px' }}>
            <div style={{ fontWeight: 'bold' }}>最小 X:</div>
            <div>{template.extent_min_x.toFixed(2)}</div>
            
            <div style={{ fontWeight: 'bold' }}>最小 Y:</div>
            <div>{template.extent_min_y.toFixed(2)}</div>
            
            <div style={{ fontWeight: 'bold' }}>最大 X:</div>
            <div>{template.extent_max_x.toFixed(2)}</div>
            
            <div style={{ fontWeight: 'bold' }}>最大 Y:</div>
            <div>{template.extent_max_y.toFixed(2)}</div>
            
            <div style={{ fontWeight: 'bold' }}>宽度:</div>
            <div>{(template.extent_max_x - template.extent_min_x).toFixed(2)}</div>
            
            <div style={{ fontWeight: 'bold' }}>高度:</div>
            <div>{(template.extent_max_y - template.extent_min_y).toFixed(2)}</div>
          </div>
        </div>
      )}

      {/* 操作按钮 */}
      <div style={{ 
        display: 'flex',
        gap: '15px',
        marginTop: '30px'
      }}>
        <a
          href={template.file_url}
          download
          style={{
            padding: '12px 24px',
            background: '#007bff',
            color: 'white',
            textDecoration: 'none',
            borderRadius: '6px',
            display: 'inline-block'
          }}
        >
          📥 下载 DXF 文件
        </a>
        
        <a
          href={template.file_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            padding: '12px 24px',
            background: '#28a745',
            color: 'white',
            textDecoration: 'none',
            borderRadius: '6px',
            display: 'inline-block'
          }}
        >
          🔗 在新窗口打开
        </a>
      </div>

      {/* 提示信息 */}
      <div style={{ 
        marginTop: '30px',
        padding: '15px',
        background: '#fff3cd',
        borderRadius: '6px',
        fontSize: '14px'
      }}>
        <strong>💡 提示：</strong>
        <ul style={{ margin: '10px 0 0 20px', paddingLeft: 0 }}>
          <li>大文件（{template.entity_count} 个实体）不适合在浏览器中预览</li>
          <li>建议下载后用 AutoCAD 或其他专业软件打开</li>
          <li>如需编辑，请使用桌面版 CAD 软件</li>
        </ul>
      </div>
    </div>
  );
}

export default DxfPreview;
