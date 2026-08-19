"""DeepSeek 余额页

展示 DeepSeek 账号余额（总余额/充值/赠送）与可用状态，只负责渲染。
数据由 main 传入（service.deepseek.get_balance() 的返回 dict）。
余额低于 ALERT_THRESHOLD 时金额告警变色。
"""
import time

from color import (
    BLACK, WHITE, GREEN, RED, ORANGE, YELLOW, CYAN, LGRAY, CARD,
)
from .dashboard import draw_page_frame

# 余额告警阈值（元），低于该值金额显示为橙色并提示
ALERT_THRESHOLD = 10.0

# 货币代码 → 符号
_CURRENCY = {'CNY': '¥', 'USD': '$'}

# 两张小卡片（充值/赠送）
_CARD_W = (320 - 12 - 8) // 2


def _sym(currency):
    return _CURRENCY.get(currency, currency + ' ')


def _fit(disp, text, size, max_w):
    """按像素宽度裁剪文本，超宽时尾部加省略号"""
    if disp.text_width_pil(text, size) <= max_w:
        return text
    while text and disp.text_width_pil(text + '\u2026', size) > max_w:
        text = text[:-1]
    return text + '\u2026'


def _status(info):
    """按余额与可用状态返回 (提示文字, 颜色)"""
    total = float(info.get('total', 0) or 0)
    sym = _sym(info.get('currency', 'CNY'))
    if not info.get('is_available'):
        return '余额不足，请充值', RED
    if total < ALERT_THRESHOLD:
        return f'余额较低 (< {sym}{ALERT_THRESHOLD:.0f})', ORANGE
    return '余额充足', GREEN


def draw_deepseek(disp, info):
    """绘制 DeepSeek 余额页。

    info: get_balance() 返回值；None 表示数据加载中。
    """
    W = disp.width
    draw_page_frame(disp, 'DeepSeek 余额')

    if info is None:
        disp.draw_text_pil(W // 2 - 32, 105, '加载中...', LGRAY, size=14)
        disp.flush()
        return

    if not info.get('ok'):
        # 查询失败：警示图标 + 错误信息
        disp.fill_circle(W // 2, 92, 22, RED)
        disp.draw_text_pil(W // 2 - 9, 84, '!', WHITE, size=18)
        err = _fit(disp, str(info.get('error', '未知错误')), 13, W - 40)
        disp.draw_text_pil(W // 2 - disp.text_width_pil(err, 13) // 2,
                           132, err, YELLOW, size=13)
        disp.draw_text_pil(W // 2 - 34, 170, '按 Esc 返回', LGRAY, size=12)
        disp.flush()
        return

    # 顶栏右侧：当前状态（黑字叠加在橙色标题栏上）
    st, _ = _status(info)
    disp.draw_text_pil(W - 14 - disp.text_width_pil(st, 10), 12, st, BLACK, size=10)

    sym = _sym(info.get('currency', 'CNY'))
    total = str(info.get('total', '0.00'))
    ts = info.get('ts', time.time())

    # 总余额大卡片
    x, y, w, h = 6, 38, W - 12, 80
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 12, y + 12, 5,
                     GREEN if info.get('is_available') else RED)
    disp.draw_text_pil(x + 23, y + 10, '总余额', LGRAY, size=10)
    _, clr = _status(info)
    money = _fit(disp, f'{sym}{total}', 30, w - 24)
    disp.draw_text_pil(x + (w - disp.text_width_pil(money, 30)) // 2,
                       y + 30, money, clr, size=30)
    disp.draw_text_pil(x + 12, y + h - 14,
                       f'上次刷新 {time.strftime("%H:%M", time.localtime(ts))}',
                       LGRAY, size=10)

    # 充值 / 赠送两列小卡片
    cy = 126
    for label, key, clr, cx in (
        ('充值余额', 'topped_up', CYAN, 6),
        ('赠送余额', 'granted', ORANGE, 6 + _CARD_W + 8),
    ):
        disp.fill_round_rect(cx, cy, _CARD_W, 56, 8, CARD)
        disp.fill_circle(cx + 12, cy + 12, 5, clr)
        disp.draw_text_pil(cx + 23, cy + 10, label, LGRAY, size=10)
        val = _fit(disp, f'{sym}{info.get(key, "0.00")}', 20, _CARD_W - 24)
        disp.draw_text_pil(cx + 12, cy + 26, val, clr, size=20)

    # 底部状态行
    sy = 190
    disp.fill_round_rect(6, sy, W - 12, 42, 8, CARD)
    st, st_clr = _status(info)
    disp.draw_text_pil(18, sy + 15, st, st_clr, size=14)
    tip = '每5分钟刷新'
    disp.draw_text_pil(W - 14 - disp.text_width_pil(tip, 10), sy + 16,
                       tip, LGRAY, size=10)

    disp.flush()
