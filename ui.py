"""ST7789 系统监控 UI

依赖 st7789_driver 提供的绘图原语，仅负责 UI 组件与仪表盘的渲染，
不读取任何系统信息（数据由 main 采集后传入）。
卡片式布局：顶栏 + CPU/内存进度条卡片 + 温度/风扇底部卡片。
"""
from color import (
    BLACK, WHITE, GREEN, RED, CYAN, ORANGE, DGRAY, LGRAY, CARD, TRACK,
)

_CW = 6  # 单字符宽度（scale=1），字符高 8


def _text_w(text, scale):
    return len(text) * _CW * scale


def _load_color(pct):
    """按负载返回颜色：绿 < 60 ≤ 橙 < 85 ≤ 红"""
    if pct < 60:
        return GREEN
    if pct < 85:
        return ORANGE
    return RED


def _temp_color(temp):
    if temp is None:
        return LGRAY
    if temp < 55:
        return GREEN
    if temp < 70:
        return ORANGE
    return RED


# ==================== UI 组件 ====================
def draw_bar(disp, x, y, w, h, pct, color):
    """圆角进度条，pct=0~100，底槽 + 彩色填充"""
    pct = max(0, min(100, pct))
    r = h // 2
    disp.fill_round_rect(x, y, w, h, r, TRACK)
    fw = int(w * pct / 100)
    if fw > 0:
        disp.fill_round_rect(x, y, max(fw, h), h, r, color)


def draw_wifi_icon(disp, x, y, quality, color=WHITE):
    """16x14 WiFi 信号图标，quality 0-100，未填充部分用暗灰色"""
    off = DGRAY
    c = color if quality >= 75 else off
    disp.fill_rect(x, y, 16, 2, c)
    c = color if quality >= 50 else off
    disp.fill_rect(x+2, y+3, 12, 2, c)
    c = color if quality >= 25 else off
    disp.fill_rect(x+4, y+6, 8, 2, c)
    c = color if quality >= 1 else off
    disp.fill_rect(x+6, y+9, 4, 2, c)
    disp.fill_rect(x+7, y+12, 2, 2, color)  # 圆点始终点亮


def _metric_card(disp, x, y, w, h, label, value, color, pct=None, note="", unit=""):
    """通用指标卡片：圆角底 + 左侧强调条 + 标题 + 大数值 (+ 进度条/单位/右上备注)"""
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 12, y + 12, 5, color)          # 左侧强调圆点
    disp.draw_text(x + 18, y + 8, label, LGRAY, 1)
    if note:
        disp.draw_text(x + w - 8 - _text_w(note, 1), y + 8, note, LGRAY, 1)
    disp.draw_text(x + 12, y + 22, value, color, 3)
    if unit:
        disp.draw_text(x + 12, y + h - 14, unit, LGRAY, 1)
    if pct is not None:
        draw_bar(disp, x + 12, y + h - 12, w - 24, 8, pct, color)


# ==================== 仪表盘绘制 ====================
def draw_dashboard(disp, cpu_pct, cpu_temp, fan_rpm,
                   mem_used, mem_total, mem_pct,
                   wifi_ssid, wifi_dbm, wifi_q):
    W = disp.width
    disp.fill_screen(BLACK)

    # --- 顶栏 ---
    disp.fill_round_rect(6, 6, W - 12, 30, 6, CARD)
    disp.draw_text(16, 13, "SYS MONITOR", CYAN, 2)
    if wifi_ssid:
        label = wifi_ssid
        draw_wifi_icon(disp, W - 28, 13, wifi_q, CYAN)
        disp.draw_text(W - 34 - _text_w(label, 1), 15, label, WHITE, 1)
    else:
        disp.draw_text(W - 14 - _text_w("WiFi --", 1), 15, "WiFi --", LGRAY, 1)

    # --- CPU / 内存 进度条卡片 ---
    _metric_card(disp, 6, 40, W - 12, 60, "CPU",
                 f"{cpu_pct:.0f}%", _load_color(cpu_pct), pct=cpu_pct)
    mem_note = f"{mem_used:.0f}/{mem_total:.0f}MB"
    _metric_card(disp, 6, 104, W - 12, 60, "MEM",
                 f"{mem_pct:.0f}%", _load_color(mem_pct), pct=mem_pct, note=mem_note)

    # --- 底部：核心温度 / 风扇转速 ---
    half = (W - 12 - 8) // 2
    temp_val = f"{cpu_temp:.0f}C" if cpu_temp is not None else "N/A"
    _metric_card(disp, 6, 170, half, 64, "CORE TEMP", temp_val, _temp_color(cpu_temp))
    fan_val = f"{fan_rpm}" if fan_rpm is not None else "N/A"
    _metric_card(disp, 6 + half + 8, 170, half, 64, "FAN", fan_val, CYAN, unit="RPM")

    disp.flush()
