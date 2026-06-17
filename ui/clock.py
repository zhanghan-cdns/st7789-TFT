"""时钟页（第二屏）

仅负责渲染，时间/日期/星期/农历等数据由 main 采集格式化后传入，
保持 UI 不读取系统信息的约定。
布局：翻页牌样式的 HH:MM（大）+ 秒（小）+ 公历日期/星期 + 农历。
"""
from color import BLACK, WHITE, CYAN, YELLOW, LGRAY, DGRAY

# 翻页卡片配色：上半较亮、下半较暗，中间留黑缝模拟翻页牌
CARD_HI = 0x3186   # 卡片上半（较亮深灰）
CARD_LO = 0x18E3   # 卡片下半（较暗深灰）


def _flip_card(disp, x, y, w, h, text, size, fg):
    """绘制单个翻页牌：上下两段圆角卡片 + 中缝，文字横跨缝隙居中"""
    r = 6
    seam = 3
    top_h = (h - seam) // 2
    disp.fill_round_rect(x, y, w, top_h, r, CARD_HI)
    disp.fill_round_rect(x, y + top_h + seam, w, h - top_h - seam, r, CARD_LO)
    tw, th = disp.text_size_pil(text, size)
    disp.draw_text_pil(x + (w - tw) // 2, y + (h - th) // 2, text, fg, size=size)


def draw_clock(disp, time_str, date_str, week_str, lunar_str):
    """绘制时钟页

    参数：
      time_str  — 时间字符串，如 "14:23:05"
      date_str  — 公历日期，如 "2026-06-16"
      week_str  — 星期，如 "周二"
      lunar_str — 农历串，如 "丙午马年 正月初一"
    """
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    # 拆分时分秒（容错：缺失补 0）
    parts = (time_str.split(':') + ['00', '00', '00'])[:3]
    hh, mm, ss = (p.zfill(2)[:2] for p in parts)

    # 翻页牌尺寸与整体布局（HH:MM 大牌 + 秒小牌，水平居中）
    cw, ch = 54, 96          # 大牌宽高
    igap = 6                 # 同组两位之间的间距
    colon_w = 22             # 冒号区宽度
    sw, sh = 40, 52          # 秒小牌宽高
    sgap = 8                 # 分钟组与秒牌的间距
    group_w = cw * 2 + igap
    total = group_w + colon_w + group_w + sgap + sw
    x = (W - total) // 2
    card_y = 42

    # 时（两位大牌）
    _flip_card(disp, x, card_y, cw, ch, hh[0], 64, WHITE)
    _flip_card(disp, x + cw + igap, card_y, cw, ch, hh[1], 64, WHITE)
    x += group_w

    # 冒号（两个 CYAN 圆点，垂直居中；秒为偶数时显示，奇数时熄灭实现闪烁）
    if int(ss) % 2 == 0:
        cx = x + colon_w // 2
        cy = card_y + ch // 2
        disp.fill_circle(cx, cy - 18, 5, CYAN)
        disp.fill_circle(cx, cy + 18, 5, CYAN)
    x += colon_w

    # 分（两位大牌）
    _flip_card(disp, x, card_y, cw, ch, mm[0], 64, WHITE)
    _flip_card(disp, x + cw + igap, card_y, cw, ch, mm[1], 64, WHITE)
    x += group_w + sgap

    # 秒（小牌，与大牌垂直居中对齐）
    _flip_card(disp, x, card_y + (ch - sh) // 2, sw, sh, ss, 28, LGRAY)

    # 公历日期/星期 + 农历，居中显示在牌下方
    date_line = f"{date_str}  {week_str}"
    dw, dh = disp.text_size_pil(date_line, 18)
    lw, lh = disp.text_size_pil(lunar_str, 20)
    y = card_y + ch + 14
    disp.draw_text_pil((W - dw) // 2, y, date_line, LGRAY, size=18)
    y += dh + 10
    disp.draw_text_pil((W - lw) // 2, y, lunar_str, YELLOW, size=20)

    # 底部切换提示
    hint = "\u2190 \u2192 \u5207\u6362"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil((W - hw) // 2, H - 14, hint, DGRAY, size=10)

    disp.flush()
