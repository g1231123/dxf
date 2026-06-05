"""
CadLike 常量定义
完全模仿 AutoCAD 的常量和枚举
"""

# =============================================================================
# 颜色常量 (ACI - AutoCAD Color Index)
# =============================================================================

acRed = 1           # 红色
acYellow = 2        # 黄色
acGreen = 3         # 绿色
acCyan = 4          # 青色
acBlue = 5          # 蓝色
acMagenta = 6       # 品红
acWhite = 7         # 白色/黑色（根据背景）
acDarkGrey = 8      # 深灰
acLightGrey = 9     # 浅灰

# 扩展颜色
acDarkRed = 10
acLightRed = 11
acDarkYellow = 12
acLightYellow = 13
acDarkGreen = 14
acLightGreen = 15
acDarkCyan = 16
acLightCyan = 17
acDarkBlue = 18
acLightBlue = 19
acDarkMagenta = 20
acLightMagenta = 21

# =============================================================================
# 对齐方式常量
# =============================================================================

# 水平对齐
acAlignmentLeft = 0
acAlignmentCenter = 1
acAlignmentRight = 2
acAlignmentAligned = 3
acAlignmentMiddle = 4
acAlignmentFit = 5

# 垂直对齐
acVerticalAlignmentBaseline = 0
acVerticalAlignmentBottom = 1
acVerticalAlignmentMiddle = 2
acVerticalAlignmentTop = 3

# =============================================================================
# 线型常量
# =============================================================================

acLineByLayer = -1
acLineByBlock = -2
acLineContinuous = "Continuous"
acLineHidden = "Hidden"
acLineCenter = "Center"
acLineDashDot = "Dashdot"
acLineBorder = "Border"
acLineDivide = "Divide"

# =============================================================================
# 填充图案类型
# =============================================================================

acHatchPatternTypePredefined = 0
acHatchPatternTypeUserDefined = 1
acHatchPatternTypeCustomDefined = 2

# =============================================================================
# 文件格式版本
# =============================================================================

ac2010 = 21
ac2013 = 23
ac2018 = 24
acDXF = 25

# =============================================================================
# 图层属性
# =============================================================================

acLayerFrozen = 1
acLayerLocked = 2
acLayerPlottable = 3

# =============================================================================
# 单位类型
# =============================================================================

acUnitless = 0
acInches = 1
acFeet = 2
acMiles = 3
acMillimeters = 4
acCentimeters = 5
acMeters = 6
acKilometers = 7

# =============================================================================
# 颜色映射字典
# =============================================================================

ACI_COLOR_MAP = {
    1: (255, 0, 0),      # Red
    2: (255, 255, 0),    # Yellow
    3: (0, 255, 0),      # Green
    4: (0, 255, 255),    # Cyan
    5: (0, 0, 255),      # Blue
    6: (255, 0, 255),    # Magenta
    7: (255, 255, 255),  # White
    8: (128, 128, 128),  # Dark Grey
    9: (192, 192, 192),  # Light Grey
}

HEX_TO_ACI = {
    "#FF0000": 1,
    "#FFFF00": 2,
    "#00FF00": 3,
    "#00FFFF": 4,
    "#0000FF": 5,
    "#FF00FF": 6,
    "#FFFFFF": 7,
    "#808080": 8,
    "#C0C0C0": 9,
    "#000000": 250,
}

ACI_TO_HEX = {
    1: "#FF0000",
    2: "#FFFF00",
    3: "#00FF00",
    4: "#00FFFF",
    5: "#0000FF",
    6: "#FF00FF",
    7: "#FFFFFF",
    8: "#808080",
    9: "#C0C0C0",
    250: "#000000",
}
