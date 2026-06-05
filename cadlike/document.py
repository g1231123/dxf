"""
CadLike 文档类
模仿 pyautocad 的 Document 对象
"""

from pathlib import Path
from typing import Optional, Union


class Document:
    """
    CAD 文档类 - 模仿 pyautocad.doc
    
    表示一个 CAD 文档，包含图层、实体等信息。
    使用 ezdxf 作为后端存储。
    
    Attributes:
        Name: 文档名称
        Layers: 图层集合
        ActiveLayer: 当前活动图层
    
    Examples:
        >>> doc = acad.doc
        >>> print(doc.Name)
        Drawing1.dxf
        >>> doc.SaveAs("output.dxf")
    """
    
    def __init__(self, acad):
        """
        初始化文档
        
        Args:
            acad: 父 Autocad 对象
        """
        self._acad = acad
        
        # 延迟导入 ezdxf
        try:
            import ezdxf
            self._ezdxf_doc = ezdxf.new("R2018")
        except ImportError:
            raise RuntimeError("ezdxf not installed. Run: pip install ezdxf")
        
        # 初始化图层集合
        from .layers import Layers
        self._layers = Layers(self)
        
        # 默认文档名
        self._name = "Drawing1.dxf"
        self._path = None
    
    @property
    def Name(self) -> str:
        """
        文档名称
        
        Returns:
            文档名称字符串
        """
        return self._name
    
    @Name.setter
    def Name(self, value: str):
        """设置文档名称"""
        self._name = str(value)
    
    @property
    def Layers(self) -> "Layers":
        """
        图层集合
        
        Returns:
            Layers 对象，用于管理图层
        """
        return self._layers
    
    @property
    def ActiveLayer(self) -> "Layer":
        """
        当前活动图层
        
        Returns:
            Layer 对象
        """
        # 从 ezdxf 获取当前图层
        layer_name = self._ezdxf_doc.header.get('$CLAYER', '0')
        return self._layers.Item(layer_name)
    
    @ActiveLayer.setter
    def ActiveLayer(self, layer):
        """
        设置当前活动图层
        
        Args:
            layer: 图层名称或 Layer 对象
        """
        if isinstance(layer, str):
            layer_name = layer
        else:
            layer_name = layer.Name
        
        # 确保图层存在
        if layer_name not in self._ezdxf_doc.layers:
            self._layers.Add(layer_name)
        
        # 设置为当前图层
        self._ezdxf_doc.header['$CLAYER'] = layer_name
    
    def SaveAs(self, filename: str, file_format: int = 24) -> None:
        """
        另存为文件
        
        Args:
            filename: 文件名（完整路径）
            file_format: 
                24 = DWG 格式（实际保存为 DXF）
                25 = DXF 格式
                
        Note:
            由于 ezdxf 只能生成 DXF，即使指定 DWG 也会保存为 DXF
        """
        self._name = Path(filename).name
        self._path = filename
        
        # 确保扩展名正确
        if file_format == 24:
            # DWG 格式请求，但 ezdxf 只能保存 DXF
            if not str(filename).lower().endswith('.dxf'):
                filename = str(filename).replace('.dwg', '.dxf')
                filename = str(filename).replace('.DWG', '.dxf')
        
        # 保存为 DXF
        self._ezdxf_doc.saveas(filename)
    
    def Save(self) -> None:
        """
        保存文档
        
        如果文档已有路径，则保存到该路径；
        否则相当于 SaveAs("Drawing1.dxf")
        """
        if self._path:
            self._ezdxf_doc.saveas(self._path)
        else:
            self.SaveAs("Drawing1.dxf")
    
    def Close(self, save_changes: bool = False) -> None:
        """
        关闭文档
        
        Args:
            save_changes: 是否保存更改
        """
        if save_changes:
            self.Save()
        
        # 清理资源
        self._ezdxf_doc = None
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Document('{self._name}')"
    
    def __str__(self) -> str:
        """格式化输出"""
        return f"CadLike Document: {self._name}"


class Documents:
    """
    文档集合类 - 模仿 acad.app.Documents
    
    管理多个打开的文档。
    """
    
    def __init__(self, acad):
        """
        初始化文档集合
        
        Args:
            acad: 父 Autocad 对象
        """
        self._acad = acad
        self._docs = []
    
    def Add(self) -> Document:
        """
        创建新文档
        
        Returns:
            新的 Document 对象
        """
        doc = Document(self._acad)
        self._docs.append(doc)
        return doc
    
    def Open(self, filename: str) -> Document:
        """
        打开现有文档
        
        Args:
            filename: 文件路径
            
        Returns:
            Document 对象
            
        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: 无法打开文件
        """
        import ezdxf
        
        filepath = Path(filename)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filename}")
        
        doc = Document(self._acad)
        doc._ezdxf_doc = ezdxf.readfile(filename)
        doc._name = filepath.name
        doc._path = str(filepath)
        
        self._docs.append(doc)
        return doc
    
    def Item(self, index_or_name):
        """
        获取文档
        
        Args:
            index_or_name: 索引（整数）或名称（字符串）
            
        Returns:
            Document 对象或 None
        """
        if isinstance(index_or_name, int):
            if 0 <= index_or_name < len(self._docs):
                return self._docs[index_or_name]
        elif isinstance(index_or_name, str):
            for doc in self._docs:
                if doc.Name == index_or_name:
                    return doc
        return None
    
    def __getitem__(self, index_or_name):
        """支持 documents[0] 或 documents["name"]"""
        result = self.Item(index_or_name)
        if result is None:
            raise KeyError(f"Document not found: {index_or_name}")
        return result
    
    def __len__(self) -> int:
        """返回文档数量"""
        return len(self._docs)
    
    def __iter__(self):
        """支持 for doc in documents"""
        return iter(self._docs)
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Documents(count={len(self._docs)})"
