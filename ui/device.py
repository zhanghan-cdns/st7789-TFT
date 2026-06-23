"""设备信息页

展示 CPU、内存、存储、运行时间等基础系统信息。
数据由 main 传入，只负责渲染。
"""
from color import BLACK, WHITE, GREEN, CYAN, YELLOW, DGRAY, CARD


def draw_device(disp, cpu_pct, cpu_temp, mem_used, mem_total, mem_pct,
                disk_used, disk_total, disk_pct, uptime):
    """绘制设备信息页"""
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, "设备信息", CYAN, size=16)

    cpu_str = f'{cpu_pct}%'
    if cpu_temp is not None:
        cpu_str += f'  {cpu_temp:.1f}°C'
    _row(disp, 6, 42, W - 12, 'CPU', cpu_str, GREEN if cpu_pct < 80 else 0xF800)

    mem_str = f'{mem_used}MB / {mem_total}MB ({mem_pct}%)'
    _row(disp, 6, 76, W - 12, '内存', mem_str, GREEN if mem_pct < 80 else YELLOW)

    disk_str = f'{disk_used}G / {disk_total}G ({disk_pct}%)'
    _row(disp, 6, 110, W - 12, '存储', disk_str, GREEN if disk_pct < 80 else YELLOW)

    _row(disp, 6, 144, W - 12, '运行时间', uptime, WHITE)

    hint = "Esc 返回"
    disp.draw_text_pil(6, H - 14, hint, DGRAY, size=10)
    disp.flush()


def _row(disp, x, y, w, label, value, color):
    """绘制一行标签 + 数值"""
    disp.fill_round_rect(x, y, w, 30, 6, CARD)
    disp.draw_text_pil(x + 12, y + 7, label, DGRAY, size=12)
    vw = disp.text_width_pil(value, 14)
    disp.draw_text_pil(x + w - 12 - vw, y + 6, value, color, size=14)
