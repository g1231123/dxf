import React, { useState } from 'react';

function UploadModal({ onClose, onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [name, setName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
      // 自动填充名称（去掉扩展名）
      if (!name) {
        const fileName = selectedFile.name.replace(/\.(dxf|dwg)$/i, '');
        setName(fileName);
      }
    }
  };

  const handleUpload = async () => {
    if (!file) {
      alert('请选择文件');
      return;
    }

    setUploading(true);
    setProgress(0);

    try {
      const formData = new FormData();
      formData.append('file', file);
      if (name) {
        formData.append('name', name);
      }

      // 使用 XMLHttpRequest 以支持进度条
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percentComplete = (e.loaded / e.total) * 100;
          setProgress(percentComplete);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          const result = JSON.parse(xhr.responseText);
          if (result.code === 0) {
            alert('上传成功！');
            onUploadSuccess(result.data);
            onClose();
          } else {
            alert('上传失败: ' + result.message);
          }
        } else {
          alert('上传失败: HTTP ' + xhr.status);
        }
        setUploading(false);
      });

      xhr.addEventListener('error', () => {
        alert('上传失败，请检查网络连接');
        setUploading(false);
      });

      xhr.open('POST', '/api/template/simple/upload');
      xhr.send(formData);

    } catch (error) {
      console.error('上传失败:', error);
      alert('上传失败: ' + error.message);
      setUploading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: 'white',
        borderRadius: '8px',
        padding: '30px',
        width: '500px',
        maxWidth: '90%',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
      }}>
        <h2 style={{ margin: '0 0 20px 0', fontSize: '20px' }}>上传 DXF/DWG 模板</h2>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
            选择文件 *
          </label>
          <input
            type="file"
            accept=".dxf,.dwg"
            onChange={handleFileChange}
            disabled={uploading}
            style={{
              width: '100%',
              padding: '10px',
              border: '1px solid #ddd',
              borderRadius: '4px'
            }}
          />
          {file && (
            <div style={{ marginTop: '8px', fontSize: '12px', color: '#666' }}>
              已选择: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
            </div>
          )}
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
            模板名称
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="不填则使用文件名"
            disabled={uploading}
            style={{
              width: '100%',
              padding: '10px',
              border: '1px solid #ddd',
              borderRadius: '4px'
            }}
          />
        </div>

        {uploading && (
          <div style={{ marginBottom: '20px' }}>
            <div style={{ marginBottom: '8px', fontSize: '14px', color: '#666' }}>
              上传进度: {progress.toFixed(0)}%
            </div>
            <div style={{
              width: '100%',
              height: '8px',
              background: '#f0f0f0',
              borderRadius: '4px',
              overflow: 'hidden'
            }}>
              <div style={{
                width: `${progress}%`,
                height: '100%',
                background: '#007bff',
                transition: 'width 0.3s'
              }} />
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={uploading}
            style={{
              padding: '10px 20px',
              border: '1px solid #ddd',
              background: 'white',
              borderRadius: '4px',
              cursor: uploading ? 'not-allowed' : 'pointer',
              opacity: uploading ? 0.5 : 1
            }}
          >
            取消
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: (!file || uploading) ? '#ccc' : '#007bff',
              color: 'white',
              borderRadius: '4px',
              cursor: (!file || uploading) ? 'not-allowed' : 'pointer'
            }}
          >
            {uploading ? '上传中...' : '上传'}
          </button>
        </div>

        <div style={{ marginTop: '20px', padding: '10px', background: '#f8f9fa', borderRadius: '4px', fontSize: '12px', color: '#666' }}>
          <strong>提示：</strong>
          <ul style={{ margin: '5px 0 0 0', paddingLeft: '20px' }}>
            <li>支持 DXF 和 DWG 格式</li>
            <li>文件直接上传，不解析实体</li>
            <li>上传速度快，秒传完成</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default UploadModal;
