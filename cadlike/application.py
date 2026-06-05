"""
CadLike 应用程序类
模仿 pyautocad 的 Application 对象
"""

from typing import Optional


class Application:
    """
    CAD 应用程序类 - 模仿 pyautocad.app
    
    表示 CAD 应用程序本身，提供应用程序级别的操作。
    
    Attributes:
        Documents: 文档集合
        ActiveDocument: 当前活动文档
        Caption: 应用程序标题
        Path: 应用程序路径
        Version: 版本信息
    
    Examples:
        >>> app = acad.app
        >>> doc = app.Documents.Add()  # 创建新文档
        >>> print(app.Version)  # 输出版本
    """
    
    def __init__(self, acad):
        """
        初始化应用程序对象
        
        Args:
            acad: 父 Autocad 对象
        """
        self._acad = acad
        from .document import Documents
        self._documents = Documents(acad)
    
    @property
    def Documents(self):
        """
        文档集合
        
        Returns:
            Documents 对象，用于管理所有打开的文档
        """
        return self._documents
    
    @property
    def ActiveDocument(self):
        """
        当前活动文档
        
        Returns:
            Document 对象
        """
        return self._acad.doc
    
    @ActiveDocument.setter
    def ActiveDocument(self, doc):
        """设置活动文档"""
        # 在 CadLike 中，实际上只有一个文档
        # 这个方法仅用于 API 兼容
        pass
    
    @property
    def Caption(self) -> str:
        """
        应用程序标题
        
        Returns:
            标题字符串
        """
        return "CadLike - Python CAD Library"
    
    @property
    def Path(self) -> str:
        """
        应用程序路径
        
        Returns:
            路径字符串
        """
        import sys
        from pathlib import Path
        return str(Path(__file__).parent)
    
    @property
    def FullName(self) -> str:
        """
        完整文件名
        
        Returns:
            完整路径
        """
        import sys
        from pathlib import Path
        return str(Path(__file__).resolve())
    
    @property
    def Name(self) -> str:
        """
        应用程序名称
        
        Returns:
            名称字符串
        """
        return "CadLike"
    
    @property
    def Version(self) -> str:
        """
        版本信息
        
        Returns:
            版本字符串
        """
        return "1.0.0"
    
    @property
    def HWND(self) -> int:
        """
        窗口句柄（仅用于 Windows 兼容）
        
        Returns:
            0（因为不是真正的 Windows 应用）
        """
        return 0
    
    @property
    def Visible(self) -> bool:
        """
        是否可见（仅用于兼容）
        
        Returns:
            True
        """
        return True
    
    @Visible.setter
    def Visible(self, value: bool):
        """设置可见性（空操作）"""
        pass
    
    def Quit(self):
        """
        退出应用程序
        
        保存所有文档并清理资源。
        """
        # 保存所有文档
        for doc in self._documents:
            try:
                doc.Save()
            except:
                pass
        
        # 清理
        self._documents._docs.clear()
    
    def ZoomExtents(self):
        """
        缩放至全图（仅用于兼容）
        
        在实际 AutoCAD 中会调整视图。
        在 CadLike 中为空操作。
        """
        pass
    
    def ZoomAll(self):
        """缩放至全图（同 ZoomExtents）"""
        self.ZoomExtents()
    
    def ZoomWindow(self, point1, point2):
        """
        窗口缩放（仅用于兼容）
        
        Args:
            point1: 窗口第一个角点
            point2: 窗口对角点
        """
        pass
    
    def ZoomScaled(self, scale: float, center=None):
        """
        按比例缩放（仅用于兼容）
        
        Args:
            scale: 缩放比例
            center: 缩放中心点（可选）
        """
        pass
    
    def Update(self):
        """更新显示（空操作）"""
        pass
    
    def Regen(self, whichViewports: int = 1):
        """
        重生成图形（空操作）
        
        Args:
            whichViewports: 视口索引
        """
        pass
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Application('{self.Name} v{self.Version}')"
    
    def __str__(self) -> str:
        """格式化输出"""
        return f"CadLike Application v{self.Version}"


# =============================================================================
# 辅助类
# =============================================================================

class Preferences:
    """
    应用程序首选项（仅用于兼容）
    
    提供 AutoCAD 首选项的兼容接口，但实际上不存储任何设置。
    """
    
    def __init__(self, app: Application):
        self._app = app
    
    @property
    def Files(self):
        """文件首选项"""
        return self
    
    @property
    def Display(self):
        """显示首选项"""
        return self
    
    @property
    def Drafting(self):
        """绘图首选项"""
        return self
    
    @property
    def Selection(self):
        """选择首选项"""
        return self
    
    @property
    def User(self):
        """用户首选项"""
        return self


class Plot:
    """
    打印设置（仅用于兼容）
    
    提供打印相关的兼容接口。
    """
    
    def __init__(self, doc):
        self._doc = doc
    
    @property
    def QuietErrorMode(self) -> bool:
        """安静错误模式"""
        return True
    
    @QuietErrorMode.setter
    def QuietErrorMode(self, value: bool):
        """设置安静错误模式"""
        pass
    
    def PlotToFile(self, plotFile: str, plotConfig: str = ""):
        """
        打印到文件（空操作）
        
        Args:
            plotFile: 输出文件名
            plotConfig: 打印配置
        """
        pass
    
    def PlotToDevice(self, plotConfig: str = ""):
        """
        打印到设备（空操作）
        
        Args:
            plotConfig: 打印配置
        """
        pass
