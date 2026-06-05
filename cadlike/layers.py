"""
CadLike 图层类
模仿 pyautocad 的 Layer 对象
"""

from typing import Optional, List, Iterator


class Layer:
    """
    CAD 图层类 - 模仿 pyautocad.Layer
    
    图层用于组织和管理图形实体，可以控制实体的可见性、颜色等。
    
    Attributes:
        Name: 图层名称
        Color: 图层颜色（ACI 索引）
        Linetype: 线型名称
        Lineweight: 线宽
        Visible: 是否可见
        Freeze: 是否冻结
        Lock: 是否锁定
        PlotStyleName: 打印样式
    
    Examples:
        >>> layer = doc.Layers.Add("MyLayer")
        >>> layer.Color = 1  # 红色
        >>> layer.Linetype = "Dashed"
        >>> circle.Layer = "MyLayer"  # 将圆放到图层上
    """
    
    def __init__(self, layer_obj):
        """
        初始化图层对象
        
        Args:
            layer_obj: 底层的 ezdxf 图层对象
        """
        self._layer = layer_obj
    
    @property
    def Name(self) -> str:
        """
        图层名称
        
        Returns:
            图层名字符串
        """
        return self._layer.dxf.name
    
    @property
    def Color(self) -> int:
        """
        图层颜色（ACI 索引）
        
        Returns:
            ACI 颜色索引（1-255）
        """
        return self._layer.dxf.color
    
    @Color.setter
    def Color(self, value: int):
        """设置图层颜色"""
        self._layer.dxf.color = int(value)
    
    @property
    def Linetype(self) -> str:
        """
        线型名称
        
        Returns:
            线型名字符串
        """
        return self._layer.dxf.linetype
    
    @Linetype.setter
    def Linetype(self, value: str):
        """设置图层线型"""
        self._layer.dxf.linetype = str(value)
    
    @property
    def Lineweight(self) -> float:
        """
        线宽
        
        Returns:
            线宽值（毫米）
        """
        return self._layer.dxf.lineweight
    
    @Lineweight.setter
    def Lineweight(self, value: float):
        """设置图层线宽"""
        self._layer.dxf.lineweight = float(value)
    
    @property
    def PlotStyleName(self) -> str:
        """
        打印样式名称
        
        Returns:
            打印样式名称
        """
        return self._layer.dxf.get('plotstyle_name', 'Normal')
    
    @PlotStyleName.setter
    def PlotStyleName(self, value: str):
        """设置打印样式"""
        self._layer.dxf.plotstyle_name = str(value)
    
    @property
    def Visible(self) -> bool:
        """
        是否可见
        
        Returns:
            True = 可见，False = 隐藏（冻结）
        """
        return not self.Freeze
    
    @Visible.setter
    def Visible(self, value: bool):
        """设置可见性"""
        self.Freeze = not value
    
    @property
    def Freeze(self) -> bool:
        """
        是否冻结
        
        Returns:
            True = 冻结，False = 未冻结
        """
        return bool(self._layer.dxf.flags & 1)
    
    @Freeze.setter
    def Freeze(self, value: bool):
        """设置冻结状态"""
        if value:
            self._layer.dxf.flags |= 1
        else:
            self._layer.dxf.flags &= ~1
    
    @property
    def Lock(self) -> bool:
        """
        是否锁定
        
        Returns:
            True = 锁定，False = 未锁定
        """
        return bool(self._layer.dxf.flags & 4)
    
    @Lock.setter
    def Lock(self, value: bool):
        """设置锁定状态"""
        if value:
            self._layer.dxf.flags |= 4
        else:
            self._layer.dxf.flags &= ~4
    
    @property
    def On(self) -> bool:
        """
        是否开启
        
        Returns:
            True = 开启，False = 关闭
        """
        return not bool(self._layer.dxf.flags & 2)
    
    @On.setter
    def On(self, value: bool):
        """设置开启状态"""
        if value:
            self._layer.dxf.flags &= ~2
        else:
            self._layer.dxf.flags |= 2
    
    @property
    def IsPlottable(self) -> bool:
        """
        是否可打印
        
        Returns:
            True = 可打印，False = 不可打印
        """
        return not bool(self._layer.dxf.flags & 8)
    
    @IsPlottable.setter
    def IsPlottable(self, value: bool):
        """设置可打印性"""
        if value:
            self._layer.dxf.flags &= ~8
        else:
            self._layer.dxf.flags |= 8
    
    def Delete(self):
        """删除图层（只有在图层为空时才能删除）"""
        # ezdxf 删除图层实现
        # 注意：如果图层上有实体，可能无法删除
        try:
            self._layer.delete()
        except Exception as e:
            raise RuntimeError(f"Cannot delete layer: {e}")
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Layer('{self.Name}')"
    
    def __str__(self) -> str:
        """格式化输出"""
        return f"Layer: {self.Name}, Color={self.Color}, Linetype={self.Linetype}"


class Layers:
    """
    图层集合类 - 模仿 acad.doc.Layers
    
    管理文档中的所有图层。
    
    Examples:
        >>> layers = doc.Layers
        >>> 
        >>> # 添加新图层
        >>> layer = layers.Add("MyLayer")
        >>> 
        >>> # 获取图层
        >>> layer = layers.Item("MyLayer")
        >>> layer = layers["MyLayer"]  # 支持索引访问
        >>> 
        >>> # 遍历所有图层
        >>> for layer in layers:
        ...     print(layer.Name)
    """
    
    def __init__(self, doc):
        """
        初始化图层集合
        
        Args:
            doc: 父 Document 对象
        """
        self._doc = doc
        self._ezdxf_layers = doc._ezdxf_doc.layers
    
    def Add(self, name: str) -> Layer:
        """
        添加新图层
        
        Args:
            name: 图层名称
            
        Returns:
            新创建的 Layer 对象
            
        Raises:
            ValueError: 如果图层名已存在
        """
        # 检查是否已存在
        if name in self._ezdxf_layers:
            # 如果已存在，返回现有图层
            return self.Item(name)
        
        # 创建新图层
        ezdxf_layer = self._ezdxf_layers.add(name)
        return Layer(ezdxf_layer)
    
    def Item(self, name: str) -> Layer:
        """
        通过名称获取图层
        
        Args:
            name: 图层名称
            
        Returns:
            Layer 对象
            
        Raises:
            KeyError: 如果图层不存在
        """
        if name not in self._ezdxf_layers:
            raise KeyError(f"Layer not found: {name}")
        
        ezdxf_layer = self._ezdxf_layers.get(name)
        return Layer(ezdxf_layer)
    
    def __getitem__(self, name: str) -> Layer:
        """
        支持 layers["name"] 语法
        
        Args:
            name: 图层名称
            
        Returns:
            Layer 对象
        """
        return self.Item(name)
    
    def __contains__(self, name: str) -> bool:
        """
        支持 "name" in layers 语法
        
        Args:
            name: 图层名称
            
        Returns:
            True/False
        """
        return name in self._ezdxf_layers
    
    def __iter__(self) -> Iterator[Layer]:
        """
        支持 for layer in layers 语法
        
        Yields:
            Layer 对象
        """
        for ezdxf_layer in self._ezdxf_layers:
            yield Layer(ezdxf_layer)
    
    def __len__(self) -> int:
        """
        返回图层数量
        
        Returns:
            图层数
        """
        return len(self._ezdxf_layers)
    
    @property
    def Count(self) -> int:
        """图层数量（兼容 pyautocad）"""
        return len(self)
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Layers(count={len(self)})"
