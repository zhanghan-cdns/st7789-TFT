"""设备信息页

展示 CPU、内存、存储、运行时间等基础系统信息。
数据由 main 传入，只负责渲染。视觉与仪表盘统一：圆点 + 标题 + 进度条 + 数值。
"""
from color import (
    BLACK, WHITE, CYAN, LGRAY, DGRAY, CARD, GREEN, ORANGE, RED,
    CPU_CLR, MEM_CLR,
)
from .dashboard import draw_bar


def _pct_color(pct):
    """按占用率取色：<60% 绿，<85% 橙，≥85% 红"""
    if pct < 60:
        return GREEN
    if pct < 85:
        return ORANGE
    return RED


def _temp_color(t):
    if t is None:
        return LGRAY
    if t < 55:
        return GREEN
    if t < 70:
        return ORANGE
    return RED


def draw_device(disp, cpu_pct, cpu_temp, mem_used, mem_total, mem_pct,
                disk_used, disk_total, disk_pct, uptime):
    """绘制设备信息页"""
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    # 顶栏：标题 + 右侧温度
    disp.fill_round_rect(6, 6, W - 12, 30, 8, CARD)
    disp.draw_text_pil(16, 12, "设备信息", CYAN, size=16)
    if cpu_temp is not None:
        temp_s = f"{cpu_temp:.1f}\u00b0C"
        tw = disp.text_width_pil(temp_s, 14)
        disp.draw_text_pil(W - 14 - tw, 13, temp_s, _temp_color(cpu_temp), size=14)

    # 三张占用率卡片（CPU / 内存 / 存储）+ 底部运行时间卡片
    cw = W - 12
    _stat(disp, 6, 42, cw, 42, 'CPU', cpu_pct, '', CPU_CLR)
    _stat(disp, 6, 90, cw, 42, '\u5185\u5b58', mem_pct,
          f'{mem_used}/{mem_total} MB', MEM_CLR)
    _stat(disp, 6, 138, cw, 42, '\u5b58\u50a8', disk_pct,
          f'{disk_used}/{disk_total} GB', CYAN)
    _info(disp, 6, 186, cw, 30, '\u8fd0\u884c\u65f6\u95f4', uptime)

    disp.draw_text_pil(6, H - 13, "Esc \u8fd4\u56de", DGRAY, size=10)
    disp.flush()


def _stat(disp, x, y, w, h, label, pct, note, dot_color):
    """占用率卡片：圆点 + 标题 +（右上 note）+ 进度条 + 百分比数值"""
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 13, y + 13, 5, dot_color)
    disp.draw_text_pil(x + 24, y + 7, label, LGRAY, size=12)
    if note:
        nw = disp.text_width_pil(note, 11)
        disp.draw_text_pil(x + w - 12 - nw, y + 8, note, LGRAY, size=11)

    val = f'{int(round(pct))}%'
    clr = _pct_color(pct)
    vw, vh = disp.text_size_pil(val, 18)
    bar_h, bar_y = 12, y + 24
    bar_w = w - 24 - 12 - vw
    if bar_w < 30:
        bar_w = 30
    draw_bar(disp, x + 12, bar_y, bar_w, bar_h, pct, clr)
    disp.draw_text_pil(x + 12 + bar_w + 12, bar_y + (bar_h - vh) // 2,
                       val, clr, size=18)


def _info(disp, x, y, w, h, label, value):
    """无进度条的信息行：左标签 + 右数值"""
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.draw_text_pil(x + 14, y + 8, label, LGRAY, size=12)
    vw = disp.text_width_pil(value, 14)
    disp.draw_text_pil(x + w - 14 - vw, y + 7, value, WHITE, size=14)
