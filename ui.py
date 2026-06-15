"""ST7789 系统监控 UI

依赖 st7789_driver 提供的绘图原语，仅负责 UI 组件与仪表盘的渲染，
不读取任何系统信息（数据由 main 采集后传入）。
布局：顶栏 + CPU/内存进度条卡片 + 底部 NET/温度/风扇 3 列卡片。
"""
from color import (
    BLACK, WHITE, GREEN, RED, CYAN, ORANGE, DGRAY, LGRAY, CARD, TRACK,
)


def _load_color(pct):
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


def _fmt_speed(bps):
    if bps >= 1_000_000:
        return f"{bps/1_000_000:.1f}M"
    if bps >= 1_000:
        return f"{bps//1_000}K"
    return f"{bps}B"


# ==================== UI 组件 ====================
def draw_bar(disp, x, y, w, h, pct, color):
    pct = max(0, min(100, pct))
    r = h // 2
    disp.fill_round_rect(x, y, w, h, r, TRACK)
    fw = int(w * pct / 100)
    if fw > 0:
        disp.fill_round_rect(x, y, max(fw, h), h, r, color)


def draw_wifi_icon(disp, x, y, quality, color=WHITE):
    off = DGRAY
    c = color if quality >= 75 else off
    disp.fill_rect(x, y, 16, 2, c)
    c = color if quality >= 50 else off
    disp.fill_rect(x+2, y+3, 12, 2, c)
    c = color if quality >= 25 else off
    disp.fill_rect(x+4, y+6, 8, 2, c)
    c = color if quality >= 1 else off
    disp.fill_rect(x+6, y+9, 4, 2, c)
    disp.fill_rect(x+7, y+12, 2, 2, color)


def _metric_card(disp, x, y, w, h, label, value, color, pct=None, note="", unit=""):
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 12, y + 12, 5, color)
    disp.draw_text_pil(x + 23, y + 8, label, LGRAY, size=10)
    if note:
        disp.draw_text_pil(x + w - 8 - disp.text_width_pil(note, 10), y + 8, note, LGRAY, size=10)
    disp.draw_text_pil(x + 12, y + 22, value, color, size=24)
    if unit:
        disp.draw_text_pil(x + 12, y + h - 14, unit, LGRAY, size=10)
    if pct is not None:
        draw_bar(disp, x + 12, y + h - 12, w - 24, 8, pct, color)


def _net_card(disp, x, y, w, h, down, up):
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 12, y + 12, 5, CYAN)
    disp.draw_text_pil(x + 23, y + 8, "NET", LGRAY, size=10)
    d_text = f"\u2193 {_fmt_speed(down)}"
    u_text = f"\u2191 {_fmt_speed(up)}"
    disp.draw_text_pil(x + 12, y + 28, d_text, GREEN, size=16)
    disp.draw_text_pil(x + 12, y + 52, u_text, CYAN, size=16)


# ==================== 仪表盘绘制 ====================
def draw_dashboard(disp, cpu_pct, cpu_temp, fan_rpm,
                   mem_used, mem_total, mem_pct,
                   wifi_ssid, wifi_dbm, wifi_q,
                   net_down=0, net_up=0):
    W = disp.width
    disp.fill_screen(BLACK)

    # --- 顶栏 ---
    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, "SYS MONITOR", CYAN, size=16)
    if wifi_ssid:
        label = wifi_ssid
        draw_wifi_icon(disp, W - 28, 11, wifi_q, CYAN)
        disp.draw_text_pil(W - 34 - disp.text_width_pil(label, 10), 15, label, WHITE, size=10)
    else:
        disp.draw_text_pil(W - 14 - disp.text_width_pil("WiFi --", 10), 15, "WiFi --", LGRAY, size=10)

    # --- CPU / 内存 进度条卡片 ---
    _metric_card(disp, 6, 38, W - 12, 54, "CPU",
                 f"{cpu_pct:.0f}%", _load_color(cpu_pct), pct=cpu_pct)
    mem_note = f"{mem_used:.0f}/{mem_total:.0f}MB"
    _metric_card(disp, 6, 96, W - 12, 54, "MEM",
                 f"{mem_pct:.0f}%", _load_color(mem_pct), pct=mem_pct, note=mem_note)

    # --- 底部：NET / 核心温度 / 风扇转速 三列 ---
    gap = 8
    card_w = (W - 12 - gap * 2) // 3
    x1, x2, x3 = 6, 6 + card_w + gap, 6 + (card_w + gap) * 2
    y_bot = 156
    h_bot = 78

    _net_card(disp, x1, y_bot, card_w, h_bot, net_down, net_up)

    temp_val = f"{cpu_temp:.0f}C" if cpu_temp is not None else "N/A"
    _metric_card(disp, x2, y_bot, card_w, h_bot, "CORE TEMP",
                 temp_val, _temp_color(cpu_temp))

    fan_val = f"{fan_rpm}" if fan_rpm is not None else "N/A"
    _metric_card(disp, x3, y_bot, card_w, h_bot, "FAN",
                 fan_val, CYAN, unit="RPM")

    disp.flush()
