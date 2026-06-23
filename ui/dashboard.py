"""系统监控仪表盘（第一屏）

依赖 st7789_driver 提供的绘图原语，仅负责 UI 组件与仪表盘的渲染，
不读取任何系统信息（数据由 main 采集后传入）。
布局：顶栏 + CPU折线图 + 内存进度条 + 底部 NET/温度/风扇 3 列卡片。
"""
import os
from color import (
    BLACK, WHITE, GREEN, RED, CYAN, ORANGE, YELLOW, DGRAY, LGRAY, CARD, TRACK,
    CPU_CLR, MEM_CLR,
)
from .svg_raster import rasterize_svg

# CPU 折线图满量程采样点数（采集端历史上限与横轴时间刻度共用）
CPU_HISTORY_LEN = 60

# 统一页面外框尺寸
PAGE_HEADER_H = 34   # 满宽橙色标题栏高度
BORDER_W = 4         # 橙色外边框宽度
PAGE_RADIUS = 8      # 外框四角圆角半径


def draw_page_frame(disp, title, title_color=BLACK):
    """绘制统一页面外框：橙色圆角外框 + 满宽橙色标题栏(黑字) + 黑色内容区。

    四个外角为圆角；标题栏下沿为直线。各页面在标题栏右侧自行叠加额外信息，
    正文从 y=PAGE_HEADER_H 之下开始，并应保持在内容区内。返回标题栏高度。
    """
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)
    # 整屏橙色圆角矩形作为外框 + 标题栏底色
    disp.fill_round_rect(0, 0, W, H, PAGE_RADIUS, ORANGE)
    # 挖出黑色内容区（下两角圆角随外框，上两角用直角贴住标题栏下沿）
    ix, iy = BORDER_W, PAGE_HEADER_H
    iw, ih = W - 2 * BORDER_W, H - PAGE_HEADER_H - BORDER_W
    ir = PAGE_RADIUS - BORDER_W
    disp.fill_round_rect(ix, iy, iw, ih, ir, BLACK)
    disp.fill_rect(ix, iy, iw, ir, BLACK)
    disp.draw_text_pil(16, 9, title, title_color, size=16)
    return PAGE_HEADER_H


def _load_color(pct):
    """按负载百分比返回颜色：<60% 绿，<85% 橙，≥85% 红"""
    if pct < 60:
        return GREEN
    if pct < 85:
        return ORANGE
    return RED


def _temp_color(temp):
    """按温度返回值颜色：<55°C 绿，<70°C 橙，≥70°C 红"""
    if temp is None:
        return LGRAY
    if temp < 55:
        return GREEN
    if temp < 70:
        return ORANGE
    return RED


def _fmt_speed(bps):
    """将字节/秒格式化为可读字符串：B、K、M 三级"""
    if bps >= 1_000_000:
        return f"{bps/1_000_000:.1f}M"
    if bps >= 1_000:
        return f"{bps//1_000}K"
    return f"{bps}B"


# ==================== UI 组件 ====================
def draw_bar(disp, x, y, w, h, pct, color):
    """绘制圆角进度条

    先画 TRACK 色底槽，再按 pct% 比例填充 color 色。
    pct 自动钳制在 0~100。
    """
    pct = max(0, min(100, pct))
    r = h // 2
    disp.fill_round_rect(x, y, w, h, r, TRACK)
    fw = int(w * pct / 100)
    if fw > 0:
        disp.fill_round_rect(x, y, max(fw, h), h, r, color)


_WIFI_CACHE = {}

def draw_wifi_icon(disp, x, y, quality, color=WHITE):
    """绘制 WiFi 信号图标（SVG 栅格化，着色绘制）

    quality（0~100）决定了点亮几格：
    75+ → 4 格，50+ → 3 格，25+ → 2 格，1+ → 1 格。
    未达阈值的使用 DGRAY 暗灰显示。
    """
    sz = 16
    key = sz
    if key not in _WIFI_CACHE:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'assets', 'wifi.svg')
        try:
            mask = rasterize_svg(path, sz)
            _WIFI_CACHE[key] = mask
        except Exception:
            _WIFI_CACHE[key] = None
    mask = _WIFI_CACHE[key]
    if mask is None:
        return
    # 信号强度决定颜色：全强度 / 暗色 / 灰色
    if quality >= 50:
        clr = color
    else:
        clr = DGRAY
    disp.blit_mask(x, y, mask, clr)


def _metric_card(disp, x, y, w, h, label, value, color, pct=None, note="", unit="", dot_color=None):
    """通用单值指标卡片

    布局（从上到下）：
      1. 圆角矩形背景（CARD 色）
      2. 左侧圆点 + 标题行（右上可选 note）
      3. 带进度条的卡片：进度条居左，数值文字居右
      4. 无进度条的卡片：大数值居中，底部可选单位

    参数：
      dot_color — 左侧圆点颜色，默认与 color 相同
      pct       — 不为 None 时显示进度条
      note      — 标题行右上角备注文字
      unit      — 底部小字单位
    """
    if dot_color is None:
        dot_color = color
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 12, y + 12, 5, dot_color)
    disp.draw_text_pil(x + 23, y + 10, label, LGRAY, size=10)
    if note:
        disp.draw_text_pil(x + w - 8 - disp.text_width_pil(note, 10), y + 10, note, LGRAY, size=10)
    if pct is not None:
        bar_h = 12
        bar_y = y + 32
        bar_gap = 14
        tw, th = disp.text_size_pil(value, 20)
        bar_w = w - 24 - bar_gap - tw
        if bar_w < 20:
            bar_w = 20
        draw_bar(disp, x + 12, bar_y, bar_w, bar_h, pct, color)
        disp.draw_text_pil(x + 12 + bar_w + bar_gap, bar_y + (bar_h - th) // 2,
                           value, color, size=20)
    else:
        disp.draw_text_pil(x + 12, y + 24, value, color, size=24)
        if unit:
            disp.draw_text_pil(x + 12, y + h - 14, unit, LGRAY, size=10)


def _net_card(disp, x, y, w, h, down, up):
    """网络流量卡片，显示下行（↓）和上行（↑）速率

    下行用 ORANGE，上行用 CYAN 区分。
    """
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 12, y + 12, 5, ORANGE)
    disp.draw_text_pil(x + 23, y + 10, "NET", LGRAY, size=10)
    d_text = f"\u2193 {_fmt_speed(down)}"
    u_text = f"\u2191 {_fmt_speed(up)}"
    disp.draw_text_pil(x + 12, y + 28, d_text, ORANGE, size=16)
    disp.draw_text_pil(x + 12, y + 52, u_text, CYAN, size=16)


# ==================== 仪表盘整体绘制 ====================
def draw_dashboard(disp, cpu_pct, cpu_history, cpu_temp, fan_val, fan_unit,
                   mem_used, mem_total, mem_pct,
                   wifi_ssid, wifi_dbm, wifi_q,
                   net_down=0, net_up=0, net_ip=None):
    """绘制完整仪表盘界面

    参数说明：
      disp       — ST7789 驱动实例
      cpu_pct    — 当前 CPU 使用率（0~100）
      cpu_history— CPU 历史数据列表（最多 60 个采样点）
      cpu_temp   — CPU 温度（°C）或 None
      fan_val    — 风扇转速值或 PWM%，或 None
      fan_unit   — 风扇单位（'RPM' / '%'），None 表示无风扇
      mem_used   — 已用内存（MB）
      mem_total  — 总内存（MB）
      mem_pct    — 内存使用率（%）
      wifi_ssid  — 当前 WiFi SSID，空字符串表示未连接
      wifi_dbm   — 信号强度（dBm）
      wifi_q     — 信号质量（0~100）
      net_down   — 下行速率（字节/秒）
      net_up     — 上行速率（字节/秒）
      net_ip     — 网络接口 IP 地址字符串，None 表示无
    """
    W = disp.width
    draw_page_frame(disp, "系统监控")

    # 顶栏右侧：WiFi 图标 + SSID + IP（黑字，叠加在橙色标题栏上）
    if wifi_ssid:
        label = wifi_ssid + (f" {net_ip}" if net_ip else "")
        draw_wifi_icon(disp, W - 28, 9, wifi_q, BLACK)
        disp.draw_text_pil(W - 34 - disp.text_width_pil(label, 10), 12, label, BLACK, size=10)
    else:
        label = "WiFi --" + (f" {net_ip}" if net_ip else "")
        disp.draw_text_pil(W - 14 - disp.text_width_pil(label, 10), 12, label, BLACK, size=10)

    # --- CPU 折线图卡片 ---
    # 卡片内从上到下：标题行（左侧圆点 + "CPU" 标签 + 右上角当前百分比）
    #               折线图区域（历史数据连线）
    disp.fill_round_rect(6, 38, W - 12, 60, 8, CARD)
    disp.fill_circle(18, 50, 5, CPU_CLR)
    disp.draw_text_pil(29, 46, "CPU", LGRAY, size=10)
    pct_text = f"{cpu_pct:.0f}%"
    disp.draw_text_pil(W - 14 - disp.text_width_pil(pct_text, 10), 46, pct_text, CPU_CLR, size=10)
    if len(cpu_history) >= 2:
        cx, cy = 12, 66
        cw = W - 24       # 充分利用卡片宽度（左右内边距各 6）
        ch = 26
        # 按固定满量程映射：横轴时间刻度恒定，最新点贴右边缘，
        # 未填满时曲线只占右侧并向左生长，避免随采样数动态拉伸/抖动。
        step = (cw - 1) / (CPU_HISTORY_LEN - 1)
        n = len(cpu_history)
        pts = []
        for i, v in enumerate(cpu_history):
            px = cx + int((cw - 1) - (n - 1 - i) * step)
            pv = max(0, min(100, v))
            py = cy + ch - 1 - int((pv / 100) * (ch - 1))
            pts.append((px, py))
        for i in range(len(pts) - 1):
            disp.draw_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1], CPU_CLR)

    # --- 内存 进度条卡片 ---
    # 复用 _metric_card，使用进度条模式
    mem_note = f"{mem_used:.0f}MB / {mem_total/1024:.1f}GB"
    _metric_card(disp, 6, 102, W - 12, 60, "MEM",
                 f"{mem_pct:.0f}%", MEM_CLR, pct=mem_pct, note=mem_note, dot_color=MEM_CLR)

    # --- 底部三列卡片：NET / 核心温度 / 风扇转速 ---
    # 每列宽度均分，8px 间隔
    gap = 8
    card_w = (W - 12 - gap * 2) // 3
    x1, x2, x3 = 6, 6 + card_w + gap, 6 + (card_w + gap) * 2
    y_bot = 166
    h_bot = 66   # 收窄 6px，给底部橙色边框让位（166+66=232 < H-4）

    # 网络流量卡片
    _net_card(disp, x1, y_bot, card_w, h_bot, net_down, net_up)

    # 温度卡片（大字体居中显示，如 "56°C"）
    disp.fill_round_rect(x2, y_bot, card_w, h_bot, 8, CARD)
    disp.fill_circle(x2 + 12, y_bot + 12, 5, RED)
    disp.draw_text_pil(x2 + 23, y_bot + 10, "CORE TEMP", LGRAY, size=10)
    if cpu_temp is not None:
        temp_str = f"{cpu_temp:.0f}\u00b0C"
        tw, th = disp.text_size_pil(temp_str, 24)
        ty = y_bot + 26 + ((h_bot - 26) - th) // 2
        disp.draw_text_pil(x2 + (card_w - tw) // 2, ty,
                           temp_str, RED, size=24)
    else:
        disp.draw_text_pil(x2 + 12, y_bot + 26, "N/A", LGRAY, size=24)

    # 风扇卡片（数值居中，单位如 "%" 或 "RPM" 跟在值后）
    disp.fill_round_rect(x3, y_bot, card_w, h_bot, 8, CARD)
    disp.fill_circle(x3 + 12, y_bot + 12, 5, YELLOW)
    disp.draw_text_pil(x3 + 23, y_bot + 10, "FAN", LGRAY, size=10)
    fan_text = f"{fan_val}{fan_unit}" if fan_val is not None else "N/A"
    tw, th = disp.text_size_pil(fan_text, 24)
    fx = x3 + (card_w - tw) // 2
    fy = y_bot + 26 + ((h_bot - 26) - th) // 2
    disp.draw_text_pil(fx, fy, fan_text, YELLOW, size=24)

    # 将所有帧缓冲内容一次刷入屏幕
    disp.flush()
