"""时钟页（第二屏）

布局：翻页牌样式的 HH:MM（大）+ 秒（小）+ 公历日期/星期 + 农历。
数字变化时播放入滑出式翻页动画。
"""
import time as _time
from color import BLACK, WHITE, CYAN, YELLOW, LGRAY, DGRAY

CARD_HI = 0x3186
CARD_LO = 0x18E3


def _draw_card_bg(disp, x, y, w, h):
    r = 6
    seam = 3
    top_h = (h - seam) // 2
    disp.fill_round_rect(x, y, w, top_h, r, CARD_HI)
    disp.fill_round_rect(x, y + top_h + seam, w, h - top_h - seam, r, CARD_LO)


def _flip_card(disp, x, y, w, h, text, size, fg):
    tw, th = disp.text_size_pil(text, size)
    _draw_card_bg(disp, x, y, w, h)
    disp.draw_text_pil(x + (w - tw) // 2, y + (h - th) // 2, text, fg, size=size)


def _animate_slide(disp, x, y, w, h, text, size, fg, frames=5):
    """新数字从下方滑入卡片（阻塞 ~200ms）"""
    tw, th = disp.text_size_pil(text, size)
    for i in range(1, frames + 1):
        dy = int(h * (1 - i / frames))
        _draw_card_bg(disp, x, y, w, h)
        disp.draw_text_pil(x + (w - tw) // 2, y + dy, text, fg, size=size)
        disp.flush()
        _time.sleep(0.04)


def draw_clock(disp, time_str, date_str, week_str, lunar_str):
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    parts = (time_str.split(':') + ['00', '00', '00'])[:3]
    hh, mm, ss = (p.zfill(2)[:2] for p in parts)

    cw, ch = 54, 96
    igap = 6
    colon_w = 22
    sw, sh = 40, 52
    sgap = 8
    group_w = cw * 2 + igap
    total = group_w + colon_w + group_w + sgap + sw
    x0 = (W - total) // 2
    card_y = 42

    # 冒号闪烁
    if int(ss) % 2 == 0:
        cx = x0 + group_w + colon_w // 2
        cy = card_y + ch // 2
        disp.fill_circle(cx, cy - 18, 5, CYAN)
        disp.fill_circle(cx, cy + 18, 5, CYAN)

    # 底部信息
    date_line = f"{date_str}  {week_str}"
    dw, _ = disp.text_size_pil(date_line, 18)
    lw, _ = disp.text_size_pil(lunar_str, 20)
    y = card_y + ch + 14
    disp.draw_text_pil((W - dw) // 2, y, date_line, LGRAY, size=18)
    y += disp.text_size_pil(date_line, 18)[1] + 10
    disp.draw_text_pil((W - lw) // 2, y, lunar_str, YELLOW, size=20)

    hint = "\u2190 \u2192 \u5207\u6362"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil((W - hw) // 2, H - 14, hint, DGRAY, size=10)

    # ── 数字卡片 ──
    cards = [
        # (x, y, w, h, text, size, fg)
        (x0,              card_y, cw, ch, hh[0], 64, WHITE),
        (x0 + cw + igap,  card_y, cw, ch, hh[1], 64, WHITE),
        (x0 + group_w + colon_w, card_y, cw, ch, mm[0], 64, WHITE),
        (x0 + group_w + colon_w + cw + igap, card_y, cw, ch, mm[1], 64, WHITE),
        (x0 + group_w + colon_w + group_w + sgap,
         card_y + (ch - sh) // 2, sw, sh, ss, 28, LGRAY),
    ]

    # 先画出所有卡片背景 + 静态数字
    for cx, cy_, cw_, ch_, text, size, fg in cards:
        _flip_card(disp, cx, cy_, cw_, ch_, text, size, fg)

    # ── 翻页动画：检测数字变化，对变化位播放入滑 ──
    prev = getattr(draw_clock, '_prev', None)
    draw_clock._prev = tuple(c[-3] for c in cards)  # 纯数字字符串

    if prev:
        for i, (cx, cy_, cw_, ch_, text, size, fg) in enumerate(cards):
            if prev[i] != text:
                _animate_slide(disp, cx, cy_, cw_, ch_, text, size, fg)

    disp.flush()
