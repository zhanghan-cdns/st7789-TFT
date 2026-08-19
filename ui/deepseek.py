"""DeepSeek 余额页（AI 状态条 + 余额 + 峰谷模式倒计时）

展示：
  - 状态条：低饱和暗色底 + 光晕大圆灯 + 浅色状态字，调用中(红)/空闲(绿)/离线·检测中(灰)，
    忙碌时显示已调用时长
  - 标题栏右侧：当前使用模型名（优先代理上报，其次 config 兜底）
  - 主余额卡：「当前余额」标签 + 金额 + 状态胶囊；第二行 当前模式 + 充值/刷新信息
  - 峰谷模式卡：梁文峰(高峰 x2) / 梁文谷(谷段 5折)，各带「进行中/后进入」切换倒计时

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

# ---- v5 深色主题配色（低饱和，融入仪表盘风格）----
# 状态条 / 模式卡 深色底
STATUS_BUSY_BG = 0x2082    # 暗红
STATUS_IDLE_BG = 0x08E2    # 暗绿
STATUS_OFF_BG  = 0x18E3    # 暗灰
MODE_PEAK_BG   = 0x2082    # 高峰卡底（暗红）
MODE_VALLEY_BG = 0x08E2    # 谷段卡底（暗绿）
# 圆灯光晕圈（中亮）
RING_BUSY      = 0x7904    # 中红
RING_IDLE      = 0x1A45    # 中绿
RING_OFF       = 0x4208    # 中灰
# 状态文字（浅色，柔和）
TXT_BUSY       = 0xFC51    # 浅红
TXT_IDLE       = 0x7F71    # 浅绿
TXT_OFF        = LGRAY
# 状态胶囊浅底
PILL_OK_BG     = 0x0942    # 绿底
PILL_LOW_BG    = 0x28C1    # 橙底
PILL_BAD_BG    = 0x2861    # 红底

# 配置文件路径（项目根目录 config.json），用于模型名兜底
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')


def _peak_schedule(now=None):
    """DeepSeek 峰谷时段（北京时间）：高峰 9:00-12:00、14:00-18:00，其余空闲。

    返回 (is_peak, switch_sec)：
      is_peak: 当前是否处于高峰（梁文峰模式）
      switch_sec: 距下一次时段切换的剩余秒数
    """
    if now is None:
        now = datetime.datetime.now()
    h = now.hour
    if (9 <= h < 12) or (14 <= h < 18):
        is_peak = True
        end_h = 12 if h < 12 else 18
        switch = now.replace(hour=end_h, minute=0, second=0, microsecond=0)
    else:
        is_peak = False
        if h < 9:
            switch = now.replace(hour=9, minute=0, second=0, microsecond=0)
        elif h < 14:
            switch = now.replace(hour=14, minute=0, second=0, microsecond=0)
        else:
            switch = (now + datetime.timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0)
    return is_peak, max(int((switch - now).total_seconds()), 0)


def _fmt_cd(sec):
    """秒 → HH:MM:SS 倒计时"""
    sec = max(int(sec), 0)
    hh, rem = divmod(sec, 3600)
    mm, ss = divmod(rem, 60)
    return f'{hh:02d}:{mm:02d}:{ss:02d}'


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
    if info.get('error'):
        return '查询失败', RED
    total = float(info.get('total', 0) or 0)
    if not info.get('is_available'):
        return '余额不足', RED
    if total < ALERT_THRESHOLD:
        return '余额较低', ORANGE
    return '余额充足', GREEN


def _traffic(ai):
    """状态条：返回 (文字, 文字色)。ai 为 None 表示数据加载中。"""
    if ai is None:
        return '检测中', TXT_OFF
    if not ai.get('ok'):
        return '离线', TXT_OFF
    if ai.get('busy'):
        return '调用中', TXT_BUSY
    return '空闲', TXT_IDLE


def _pill_bg(clr):
    """状态胶囊底色：按文字颜色映射浅色底"""
    return {GREEN: PILL_OK_BG, ORANGE: PILL_LOW_BG,
            RED: PILL_BAD_BG}.get(clr, STATUS_OFF_BG)


def _default_model():
    """从 config.json 读模型名兜底（ai_monitor.model）"""
    try:
        with open(_CONFIG_PATH, 'r') as f:
            return ((json.load(f).get('ai_monitor') or {}).get('model') or '').strip()
    except Exception:
        return ''


def _ink_y(disp, text, size, cy):
    """按“墨水中心”垂直居中：返回 draw_text_pil 的 y，使文字可见部分中心对齐 cy。
    基于字体包围盒的上/下留白计算，避免 Heavy 字体顶部留白大导致偏位。"""
    _, h, asc, _ = disp.text_metrics_pil(text, size)
    return cy - (h + asc) // 2


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


def _draw_status(disp, ai):
    """状态条：低饱和暗色底 + 光晕圆灯 + 浅色状态字 + 忙碌时长"""
    label, clr = _traffic(ai)
    if ai and ai.get('busy'):
        bg, ring, lamp = STATUS_BUSY_BG, RING_BUSY, RED
    elif ai and ai.get('ok'):
        bg, ring, lamp = STATUS_IDLE_BG, RING_IDLE, GREEN
    else:
        bg, ring, lamp = STATUS_OFF_BG, RING_OFF, LGRAY

    x, y, w, h = 6, 38, disp.width - 12, 42
    cy = y + h // 2
    disp.fill_round_rect(x, y, w, h, 8, bg)
    # 光晕 + 圆灯（28px 光晕圈 + 16px 灯）
    disp.fill_circle(x + 14 + 13, cy, 13, ring)
    disp.fill_circle(x + 14 + 13, cy, 8, lamp)
    # 状态文字（16px，墨水中心与圆灯中心对齐）
    disp.draw_text_pil(x + 14 + 28 + 12, _ink_y(disp, label, 16, cy), label,
                       clr, size=16)
    # 忙碌时长（右侧，墨水中心对齐）
    if ai and ai.get('busy') and ai.get('busy_sec', 0):
        sec = int(ai['busy_sec'])
        dur = f'已 {sec // 60:02d}:{sec % 60:02d}'
        disp.draw_text_pil(x + w - 12 - disp.text_width_pil(dur, 12),
                           _ink_y(disp, dur, 12, cy), dur, WHITE, size=12)


def _draw_balance_card(disp, info, is_peak):
    """主余额卡：当前余额标签+胶囊 ／ 金额+模式 ／ 充值刷新"""
    W = disp.width
    x, y, w, h = 6, 84, W - 12, 98
    disp.fill_round_rect(x, y, w, h, 10, CARD)

    sym = _sym(info.get('currency', 'CNY'))
    total = str(info.get('total', '0.00'))
    ts = info.get('ts', time.time())

    # 第一行：左「当前余额」标签 / 右 状态胶囊
    disp.draw_text_pil(x + 14, y + 12, '当前余额', LGRAY, size=10)
    st, st_clr = _status(info)
    pill_w = disp.text_width_pil(st, 11) + 18
    pill_h = 22
    pill_cy = y + 12 + 11 // 2  # 胶囊与标签行墨水中心对齐
    disp.fill_round_rect(x + w - 14 - pill_w, pill_cy - pill_h // 2,
                         pill_w, pill_h, 11, _pill_bg(st_clr))
    disp.draw_text_pil(x + w - 14 - pill_w + 9, _ink_y(disp, st, 11, pill_cy),
                       st, st_clr, size=11)

    # 第二行：金额 + 模式名（金额下移留出呼吸感，模式紧跟金额右侧，墨水中心对齐）
    money = _fit(disp, f'{sym}{total}', 32, w - 160)
    money_clr = GREEN if float(info.get('total', 0) or 0) >= ALERT_THRESHOLD \
        else ORANGE
    my = y + 34
    disp.draw_text_pil(x + 14, my, money, money_clr, size=32)
    mode_clr = TXT_BUSY if is_peak else TXT_IDLE
    mode_txt = '梁文峰模式' if is_peak else '梁文谷模式'
    mx = x + 14 + disp.text_width_pil(money, 32) + 12
    _, mh, masc, _ = disp.text_metrics_pil(money, 32)  # 金额墨水中心
    disp.draw_text_pil(mx, _ink_y(disp, mode_txt, 12,
                                  my + (mh + masc) // 2),
                       mode_txt, mode_clr, size=12)

    # 第三行：充值+刷新
    info_txt = (f'充值 {sym}{info.get("topped_up", "0.00")} · '
                f'刷新 {time.strftime("%H:%M", time.localtime(ts))}')
    disp.draw_text_pil(x + 14, y + 78, info_txt, LGRAY, size=10)


def _draw_mode_card(disp, cx, cy, w, h, name, tag, active, switch_sec, clr, bg):
    """峰/谷模式卡：顶部 模式名 / 价格标签，底部 进行中/后进入 + 倒计时"""
    disp.fill_round_rect(cx, cy, w, h, 10, bg)
    # 顶部：模式名 + 价格标签
    disp.draw_text_pil(cx + 12, cy + 7, name, LGRAY, size=10)
    price = tag.split()[-1] if ' ' in tag else tag
    disp.draw_text_pil(cx + w - 10 - disp.text_width_pil(price, 10), cy + 7,
                       price, LGRAY, size=10)
    # 底部状态 + 倒计时
    st = f'{"进行中" if active else "后进入"} {_fmt_cd(switch_sec)}'
    st = _fit(disp, st, 13, w - 24)
    disp.draw_text_pil(cx + 12, cy + 24, st, clr, size=13)


def draw_deepseek(disp, info, ai=None):
    """绘制 DeepSeek 余额页。

    info: get_balance() 返回值；None 表示余额数据加载中。
    ai:   get_ai_state() 返回值；None 表示 AI 状态加载中。
    """
    W = disp.width
    draw_page_frame(disp, 'DeepSeek 余额')
    _draw_model(disp, ai)
    _draw_status(disp, ai)

    # ---------- 余额未加载 / 查询失败 ----------
    if info is None:
        disp.draw_text_pil(W // 2 - 32, 130, '加载中...', LGRAY, size=14)
        disp.flush()
        return

    if not info.get('ok'):
        # API 失效（如 Key 无效）：不显示错误页，降级为金额 0 + 查询失败胶囊
        info = {'ok': True, 'is_available': False, 'currency': 'CNY',
                'total': '0.00', 'granted': '0.00', 'topped_up': '0.00',
                'error': '查询失败', 'ts': info.get('ts', time.time())}

    is_peak, switch_sec = _peak_schedule()

    # ---------- 主余额卡 ----------
    _draw_balance_card(disp, info, is_peak)

    # ---------- 峰谷模式卡 ----------
    cy, ch = 186, 48
    cw = (W - 12 - 6) // 2
    _draw_mode_card(disp, 6, cy, cw, ch, '梁文峰', '高峰 x2', is_peak,
                    switch_sec, TXT_BUSY, MODE_PEAK_BG)
    _draw_mode_card(disp, 6 + cw + 6, cy, cw, ch, '梁文谷', '谷段 5折',
                    not is_peak, switch_sec, TXT_IDLE, MODE_VALLEY_BG)

    disp.flush()
