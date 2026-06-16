"""UI 包

按屏幕拆分：
  dashboard — 第一屏：系统监控仪表盘
  clock     — 第二屏：时钟（含农历）
  lunar     — 农历换算（供 clock / main 使用）

对外重导出常用入口，保持 `from ui import ...` 的调用方式不变。
"""
from .dashboard import draw_dashboard, CPU_HISTORY_LEN
from .clock import draw_clock
from .lunar import lunar_date_str
from .services import draw_services

__all__ = [
    'draw_dashboard',
    'draw_clock',
    'draw_services',
    'CPU_HISTORY_LEN',
    'lunar_date_str',
]
