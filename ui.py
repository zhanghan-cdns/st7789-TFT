"""ST7789 系统监控 UI

依赖 st7789_driver 提供的绘图原语，仅负责 UI 组件与仪表盘的渲染，
不读取任何系统信息（数据由 main 采集后传入）。
"""
from st7789_driver import (
    BLACK, WHITE, GREEN, BLUE, CYAN, MAGENTA, YELLOW, DGRAY, LGRAY,
)


# ==================== UI 组件 ====================
def draw_hbar(disp, x, y, w, h, pct, fg, bg):
    """绘制带边框的横向进度条，pct=0~100"""
    disp.fill_rect(x, y, w, h, bg)
    disp.fill_rect(x, y, int(w * pct / 100), h, fg)
    for i in range(w):
        disp.draw_pixel(x+i, y, WHITE)
        disp.draw_pixel(x+i, y+h-1, WHITE)
    for i in range(h):
        disp.draw_pixel(x, y+i, WHITE)
        disp.draw_pixel(x+w-1, y+i, WHITE)


def draw_wifi_icon(disp, x, y, quality, color=WHITE):
    """16x14 WiFi 信号图标，quality 0-100，未填充部分用暗灰色"""
    off = DGRAY
    # 4层信号弧 + 底部圆点
    c = color if quality >= 75 else off
    disp.fill_rect(x, y, 16, 2, c)
    c = color if quality >= 50 else off
    disp.fill_rect(x+2, y+3, 12, 2, c)
    c = color if quality >= 25 else off
    disp.fill_rect(x+4, y+6, 8, 2, c)
    c = color if quality >= 1 else off
    disp.fill_rect(x+6, y+9, 4, 2, c)
    disp.fill_rect(x+7, y+12, 2, 2, color)  # 圆点始终点亮


# ==================== 仪表盘绘制 ====================
def draw_dashboard(disp, cpu_pct, cpu_temp, mem_used, mem_total, mem_pct, wifi_ssid, wifi_dbm, wifi_q):
    disp.fill_screen(BLACK)
    bw = disp.width - 60
    # --- CPU 标签 + WiFi 图标(右上角) ---
    disp.draw_text(10, 8, "CPU", CYAN, 2)
    if wifi_ssid:
        wifi_text = f"{wifi_ssid[:10]} {wifi_dbm}dBm"
        tw = len(wifi_text) * 6  # scale=1, 6px/char
        disp.draw_text(disp.width - 22 - tw, 10, wifi_text, WHITE, 1)
        draw_wifi_icon(disp, disp.width - 22, 6, wifi_q, CYAN)
    else:
        disp.draw_text(disp.width - 110, 10, "WiFi: --", LGRAY, 1)
    # --- CPU 进度条 ---
    draw_hbar(disp, 10, 32, bw, 28, cpu_pct, GREEN, DGRAY)
    disp.draw_text(10, 66, f"{cpu_pct:.1f}%", GREEN, 3)
    disp.draw_text(disp.width - 100, 66, cpu_temp, YELLOW, 2)
    # --- 分割线 ---
    disp.fill_rect(10, 100, disp.width - 20, 2, LGRAY)
    # --- 内存区域 ---
    disp.draw_text(10, 110, "MEM", MAGENTA, 2)
    draw_hbar(disp, 10, 134, bw, 28, mem_pct, BLUE, DGRAY)
    disp.draw_text(10, 168, f"{mem_pct:.1f}%", BLUE, 3)
    disp.draw_text(disp.width - 210, 168, f"{mem_used:.0f}MB/{mem_total:.0f}MB", LGRAY, 2)
    disp.flush()
