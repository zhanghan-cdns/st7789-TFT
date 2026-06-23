"""设备信息页

展示板型、CPU 型号、内存/存储容量、系统、内核等设备静态规格。
数据由 main 传入（get_device_info() 的字典），只负责渲染。
"""
from color import (
    BLACK, WHITE, CYAN, LGRAY, DGRAY, CARD, GREEN, ORANGE,
    CPU_CLR, MEM_CLR,
)


def _fit(disp, text, size, max_w):
    """按像素宽度裁剪文本，超宽时尾部加省略号"""
    if max_w <= 0:
        return ''
    if disp.text_width_pil(text, size) <= max_w:
        return text
    while text and disp.text_width_pil(text + '\u2026', size) > max_w:
        text = text[:-1]
    return text + '\u2026'


def draw_device(disp, info):
    """绘制设备信息页（info 为 get_device_info() 返回的字典）"""
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    # 顶栏：标题 + 右侧主机名
    disp.fill_round_rect(6, 6, W - 12, 28, 8, CARD)
    disp.draw_text_pil(16, 10, "\u8bbe\u5907\u4fe1\u606f", CYAN, size=16)
    host = info.get('hostname', '--')
    hw = disp.text_width_pil(host, 12)
    disp.draw_text_pil(W - 14 - hw, 12, host, LGRAY, size=12)

    cores = info.get('cpu_cores', 0)
    arch = info.get('cpu_arch', '--')
    rows = [
        ('\u8bbe\u5907', info.get('board', '--'), GREEN),
        ('CPU', info.get('cpu_model', '--'), CPU_CLR),
        ('\u6838\u5fc3', f'{cores} \u6838 \u00b7 {arch}' if cores else arch, CYAN),
        ('\u5185\u5b58', info.get('mem_total', '--'), MEM_CLR),
        ('\u5b58\u50a8', info.get('disk_total', '--'), CYAN),
        ('\u7cfb\u7edf', info.get('os', '--'), ORANGE),
        ('\u5185\u6838', info.get('kernel', '--'), LGRAY),
    ]
    x, w, h, step = 6, W - 12, 24, 26
    y = 38
    for label, value, dot in rows:
        _row(disp, x, y, w, h, label, value, dot)
        y += step

    disp.draw_text_pil(6, H - 13, "Esc \u8fd4\u56de", DGRAY, size=10)
    disp.flush()


def _row(disp, x, y, w, h, label, value, dot):
    """信息行：圆点 + 左标签 + 右数值（数值过长尾部省略）"""
    disp.fill_round_rect(x, y, w, h, 6, CARD)
    disp.fill_circle(x + 12, y + h // 2, 4, dot)
    disp.draw_text_pil(x + 22, y + (h - 12) // 2, label, LGRAY, size=12)
    lw = disp.text_width_pil(label, 12)
    val_x0 = x + 22 + lw + 10
    max_w = (x + w - 10) - val_x0
    val = _fit(disp, str(value), 13, max_w)
    vw = disp.text_width_pil(val, 13)
    disp.draw_text_pil(x + w - 10 - vw, y + (h - 13) // 2, val, WHITE, size=13)
