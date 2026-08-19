"""DeepSeek 余额页（AI 红绿灯横幅 + 余额 + 峰谷模式）

展示：
  - 整行红绿灯横幅：调用中(红) / 空闲(绿) / 离线·检测中(灰)，大圆灯 + 大字，
    忙碌时显示已调用时长
  - 标题栏右侧：当前使用模型名（优先代理上报，其次 config 兜底）
  - 主余额卡：第一行 金额 + 状态胶囊；第二行 当前模式 + 充值/刷新信息
  - 峰谷模式卡：梁文峰(高峰) / 梁文谷(空闲)，显示 进行中/稍后进入

数据由 main 传入：
  info: service.deepseek.get_balance() 的返回 dict
  ai:   service.deepseek.get_ai_state() 的返回 dict（None 表示加载中）
本模块只负责渲染，不发起任何网络请求。
"""
import datetime
import json
import os
import time

from color import (
    BLACK, WHITE, GREEN, RED, ORANGE, YELLOW, LGRAY, CARD,
)
from .dashboard import draw_page_frame

# 余额告警阈值（元），低于该值金额提示为橙色
ALERT_THRESHOLD = 10.0

# 货币代码 → 符号
_CURRENCY = {'CNY': '¥', 'USD': '$'}

# 红绿灯横幅三种底色（深色，配亮圆灯 + 白字）
BANNER_BUSY = 0x7010    # 深红
BANNER_IDLE = 0x05A0    # 深绿
BANNER_OFF  = 0x4208    # 深灰

# 状态胶囊底色（配对应亮色文字）
PILL_OK = 0x0E60        # 绿底
PILL_LOW = 0x8A20       # 橙底
PILL_BAD = 0x8800       # 红底

# 配置文件路径（项目根目录 config.json），用于模型名兜底
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')


def _is_peak(now=None):
    """DeepSeek 峰谷时段（北京时间）：高峰 9:00-12:00、14:00-18:00，其余空闲。
    返回 True=高峰（梁文峰），False=空闲（梁文谷）。
    """
    if now is None:
        now = datetime.datetime.now()
    h = now.hour
    return (9 <= h < 12) or (14 <= h < 18)


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
    if not info.get('is_available'):
        return '余额不足', RED
    if total < ALERT_THRESHOLD:
        return '余额较低', ORANGE
    return '余额充足', GREEN


def _traffic(ai):
    """红绿灯：返回 (文字, 颜色)。ai 为 None 表示数据加载中。"""
    if ai is None:
        return '检测中', LGRAY
    if not ai.get('ok'):
        return '离线', LGRAY
    if ai.get('busy'):
        return '调用中', RED
    return '空闲', GREEN


def _pill_bg(clr):
    """状态胶囊底色：按文字颜色映射深色底"""
    return {GREEN: PILL_OK, ORANGE: PILL_LOW, RED: PILL_BAD}.get(clr, BANNER_OFF)


def _default_model():
    """从 config.json 读模型名兜底（ai_monitor.model）"""
    try:
        with open(_CONFIG_PATH, 'r') as f:
            return ((json.load(f).get('ai_monitor') or {}).get('model') or '').strip()
    except Exception:
        return ''


# ---- 绘制 ----

def _draw_model(disp, ai):
    """标题栏右侧显示当前模型名（黑字叠橙色标题栏）"""
    m = ''
    if ai and ai.get('model'):
        m = str(ai['model']).strip()
    if not m:
        m = _default_model()
    if not m:
        m = '--'
    m = _fit(disp, m, 10, 130)
    disp.draw_text_pil(disp.width - 8 - disp.text_width_pil(m, 10),
                       12, m, BLACK, size=10)


def _draw_banner(disp, ai):
    """整行红绿灯横幅：深色底 + 大圆灯 + 大字 + 忙碌时长"""
    label, clr = _traffic(ai)
    if ai and ai.get('busy'):
        bg = BANNER_BUSY
    elif ai and ai.get('ok'):
        bg = BANNER_IDLE
    else:
        bg = BANNER_OFF

    x, y, w, h = 6, 38, disp.width - 12, 44
    disp.fill_round_rect(x, y, w, h, 8, bg)
    # 大圆灯（28px）
    disp.fill_circle(x + 14 + 14, y + h // 2, 14, clr)
    # 状态文字（17px，垂直居中）
    disp.draw_text_pil(x + 14 + 28 + 12, y + (h - 22) // 2 + 1, label,
                       WHITE, size=17)
    # 忙碌时长（右侧）
    if ai and ai.get('busy') and ai.get('busy_sec', 0):
        sec = int(ai['busy_sec'])
        dur = f'已 {sec // 60:02d}:{sec % 60:02d}'
        disp.draw_text_pil(x + w - 12 - disp.text_width_pil(dur, 12),
                           y + (h - 16) // 2, dur, WHITE, size=12)


def _draw_balance_card(disp, info, is_peak):
    """主余额卡：金额+状态胶囊 ／ 模式名+充值刷新"""
    W = disp.width
    x, y, w, h = 6, 86, W - 12, 78
    disp.fill_round_rect(x, y, w, h, 8, CARD)

    sym = _sym(info.get('currency', 'CNY'))
    total = str(info.get('total', '0.00'))
    ts = info.get('ts', time.time())

    # 第一行：左金额 / 右状态胶囊（按实际文本高度垂直居中）
    money = _fit(disp, f'{sym}{total}', 32, w - 150)
    _, mh = disp.text_size_pil(money, 32)
    row1_y = y + 12
    disp.draw_text_pil(x + 14, row1_y, money, WHITE, size=32)
    st, st_clr = _status(info)
    pill_w = disp.text_width_pil(st, 11) + 18
    pill_h = 22
    pill_y = row1_y + (mh - pill_h) // 2
    disp.fill_round_rect(x + w - 14 - pill_w, pill_y, pill_w, pill_h, 11,
                         _pill_bg(st_clr))
    disp.draw_text_pil(x + w - 14 - pill_w + 9, pill_y + 4, st, st_clr, size=11)

    # 第二行：左 模式名(带圆点) / 右 充值+刷新（紧贴第一行底部 + 8px）
    row2_y = row1_y + mh + 8
    mode_clr = RED if is_peak else GREEN
    mode_txt = '梁文峰模式' if is_peak else '梁文谷模式'
    disp.fill_circle(x + 18, row2_y + 8, 4, mode_clr)
    disp.draw_text_pil(x + 27, row2_y + 1, mode_txt, mode_clr, size=12)
    info_txt = (f'充值 {sym}{info.get("topped_up", "0.00")} · '
                f'刷新 {time.strftime("%H:%M", time.localtime(ts))}')
    disp.draw_text_pil(x + w - 14 - disp.text_width_pil(info_txt, 10),
                       row2_y + 2, info_txt, LGRAY, size=10)


def _draw_mode_card(disp, cx, cy, w, h, name, tag, active, clr):
    """峰/谷模式卡：顶部 点+模式名 / 标签，底部 进行中/稍后进入"""
    disp.fill_round_rect(cx, cy, w, h, 8, CARD)
    # 顶部
    disp.fill_circle(cx + 16, cy + 15, 4, clr)
    disp.draw_text_pil(cx + 26, cy + 9, name, LGRAY, size=11)
    disp.draw_text_pil(cx + w - 10 - disp.text_width_pil(tag, 10), cy + 10,
                       tag, LGRAY, size=10)
    # 底部状态
    st = '进行中' if active else '稍后进入'
    disp.draw_text_pil(cx + 12, cy + 27, st, clr, size=15)


def draw_deepseek(disp, info, ai=None):
    """绘制 DeepSeek 余额页。

    info: get_balance() 返回值；None 表示余额数据加载中。
    ai:   get_ai_state() 返回值；None 表示 AI 状态加载中。
    """
    W = disp.width
    draw_page_frame(disp, 'DeepSeek 余额')
    _draw_model(disp, ai)
    _draw_banner(disp, ai)

    # ---------- 余额未加载 / 查询失败 ----------
    if info is None:
        disp.draw_text_pil(W // 2 - 32, 130, '加载中...', LGRAY, size=14)
        disp.flush()
        return

    if not info.get('ok'):
        disp.fill_circle(W // 2, 115, 22, RED)
        disp.draw_text_pil(W // 2 - 9, 107, '!', WHITE, size=18)
        err = _fit(disp, str(info.get('error', '未知错误')), 13, W - 40)
        disp.draw_text_pil(W // 2 - disp.text_width_pil(err, 13) // 2,
                           160, err, YELLOW, size=13)
        disp.draw_text_pil(W // 2 - 34, 200, '按 Esc 返回', LGRAY, size=12)
        disp.flush()
        return

    is_peak = _is_peak()

    # ---------- 主余额卡 ----------
    _draw_balance_card(disp, info, is_peak)

    # ---------- 峰谷模式卡 ----------
    cy, ch = 168, 54
    cw = (W - 12 - 6) // 2
    _draw_mode_card(disp, 6, cy, cw, ch, '梁文峰', '高峰 x2', is_peak, RED)
    _draw_mode_card(disp, 6 + cw + 6, cy, cw, ch, '梁文谷', '谷段 5折',
                    not is_peak, GREEN)

    disp.flush()
