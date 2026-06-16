"""时钟页（第二屏）

仅负责渲染，时间/日期/星期/农历等数据由 main 采集格式化后传入，
保持 UI 不读取系统信息的约定。
布局：顶栏标题 + 居中大字号时间 + 公历日期/星期 + 农历。
"""
from color import BLACK, WHITE, CYAN, YELLOW, LGRAY, DGRAY, CARD


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

    # 顶栏标题
    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, "时钟", CYAN, size=16)

    # 主体大卡片
    card_y, card_h = 42, H - 48
    disp.fill_round_rect(6, card_y, W - 12, card_h, 8, CARD)

    # 时间 + 公历日期 + 农历，整体在卡片内垂直居中
    date_line = f"{date_str}  {week_str}"
    tw, th = disp.text_size_pil(time_str, 56)
    dw, dh = disp.text_size_pil(date_line, 18)
    lw, lh = disp.text_size_pil(lunar_str, 20)
    gap1, gap2 = 16, 10
    block_h = th + gap1 + dh + gap2 + lh
    y = card_y + (card_h - block_h) // 2

    disp.draw_text_pil((W - tw) // 2, y, time_str, WHITE, size=56)
    y += th + gap1
    disp.draw_text_pil((W - dw) // 2, y, date_line, LGRAY, size=18)
    y += dh + gap2
    disp.draw_text_pil((W - lw) // 2, y, lunar_str, YELLOW, size=20)

    # 底部切换提示
    hint = "\u2190 \u2192 \u5207\u6362"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil((W - hw) // 2, card_y + card_h - 16, hint, DGRAY, size=10)

    disp.flush()
