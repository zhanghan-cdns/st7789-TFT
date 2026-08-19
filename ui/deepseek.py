"""DeepSeek 余额页（含 AI 红绿灯 + 峰谷模式 + 今日 token 消耗曲线）

展示：
  - 标题栏右侧红绿灯：调用中(红) / 空闲(绿) / 离线·检测中(灰)
  - 总余额大卡片（含充值余额 + 可用状态，低于告警阈值变色）
  - 梁文峰模式（高峰 9:00-12:00、14:00-18:00，价格 x2）与
    梁文谷模式（空闲时段，价格半价）两张模式卡，各带切换倒计时
  - 今日 token 消耗曲线（24h 柱状图，当前小时高亮）

数据由 main 传入：
  info: service.deepseek.get_balance() 的返回 dict
  ai:   service.deepseek.get_ai_state() 的返回 dict（None 表示加载中）
本模块只负责渲染，不发起任何网络请求。
"""
import datetime
import time

from color import (
    BLACK, WHITE, GREEN, RED, ORANGE, YELLOW, CYAN, LGRAY, DGRAY, CARD,
)
from .dashboard import draw_page_frame

# 余额告警阈值（元），低于该值金额显示为橙色并提示
ALERT_THRESHOLD = 10.0

# 货币代码 → 符号
_CURRENCY = {'CNY': '¥', 'USD': '$'}

# 两张模式卡片宽
_CARD_W = (320 - 12 - 8) // 2


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
    total = float(info.get('total', 0) or 0)
    sym = _sym(info.get('currency', 'CNY'))
    if not info.get('is_available'):
        return '余额不足，请充值', RED
    if total < ALERT_THRESHOLD:
        return f'余额较低 (< {sym}{ALERT_THRESHOLD:.0f})', ORANGE
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


def _fmt_tokens(n):
    """token 数量缩写：123 → 123，23456 → 23.5K，1234567 → 1.2M"""
    try:
        n = int(n)
    except Exception:
        return '--'
    if n >= 1000000:
        return f'{n / 1000000:.1f}M'
    if n >= 1000:
        return f'{n / 1000:.1f}K'
    return str(n)


def _draw_header_light(disp, ai):
    """标题栏右侧绘制红绿灯（圆点 + 状态文字，黑字叠在橙色标题栏上）"""
    label, clr = _traffic(ai)
    tw = disp.text_width_pil(label, 10)
    disp.fill_circle(disp.width - 14 - tw - 9, 18, 4, clr)
    disp.draw_text_pil(disp.width - 14 - tw, 12, label, BLACK, size=10)


def _draw_mode_card(disp, cx, cy, w, h, name, tag, active, switch_sec, clr):
    """峰/谷模式卡：圆点 + 模式名 + 标签 + 状态/倒计时"""
    disp.fill_round_rect(cx, cy, w, h, 8, CARD)
    disp.fill_circle(cx + 12, cy + 12, 5, clr)
    disp.draw_text_pil(cx + 23, cy + 10, name, LGRAY, size=10)
    disp.draw_text_pil(cx + w - 8 - disp.text_width_pil(tag, 10), cy + 10,
                       tag, LGRAY, size=10)
    if active:
        st = f'进行中 {_fmt_cd(switch_sec)}'
    else:
        st = f'后进入 {_fmt_cd(switch_sec)}'
    st = _fit(disp, st, 13, w - 24)
    disp.draw_text_pil(cx + 12, cy + 27, st, clr, size=13)


def _draw_chart(disp, hourly, y=178, h=54):
    """今日 24h token 消耗柱状图（x 自动适配屏幕宽度）"""
    W = disp.width
    x = 12
    w = W - 24
    # 底部轴线
    disp.draw_line(x, y + h - 1, x + w, y + h - 1, DGRAY)

    vals = [t.get('total', 0) for t in hourly] if hourly else []
    if not vals:
        disp.draw_text_pil(W // 2 - 30, y + h // 2 - 6, '等待数据...', LGRAY, size=12)
        return
    maxv = max(vals) if vals else 0
    cur_hour = time.localtime().tm_hour
    slot = w // len(vals)
    for i, v in enumerate(vals):
        bx = x + i * slot
        if v <= 0:
            disp.fill_rect(bx + 1, y + h - 2, slot - 2, 2, DGRAY)
            continue
        bh = int(h * v / maxv) if maxv else 1
        bh = max(bh, 2)
        clr = YELLOW if i == cur_hour else CYAN
        disp.fill_rect(bx + 1, y + h - bh, slot - 2, bh, clr)


def draw_deepseek(disp, info, ai=None):
    """绘制 DeepSeek 余额页。

    info: get_balance() 返回值；None 表示余额数据加载中。
    ai:   get_ai_state() 返回值；None 表示 AI 状态加载中。
    """
    W = disp.width
    draw_page_frame(disp, 'DeepSeek 余额')
    _draw_header_light(disp, ai)

    # ---------- 余额未加载 / 查询失败 ----------
    if info is None:
        disp.draw_text_pil(W // 2 - 32, 105, '加载中...', LGRAY, size=14)
        disp.flush()
        return

    if not info.get('ok'):
        disp.fill_circle(W // 2, 92, 22, RED)
        disp.draw_text_pil(W // 2 - 9, 84, '!', WHITE, size=18)
        err = _fit(disp, str(info.get('error', '未知错误')), 13, W - 40)
        disp.draw_text_pil(W // 2 - disp.text_width_pil(err, 13) // 2,
                           132, err, YELLOW, size=13)
        disp.draw_text_pil(W // 2 - 34, 170, '按 Esc 返回', LGRAY, size=12)
        disp.flush()
        return

    sym = _sym(info.get('currency', 'CNY'))
    total = str(info.get('total', '0.00'))
    ts = info.get('ts', time.time())
    is_peak, switch_sec = _peak_schedule()

    # ---------- 总余额大卡片 ----------
    x, y, w, h = 6, 38, W - 12, 64
    disp.fill_round_rect(x, y, w, h, 8, CARD)
    disp.fill_circle(x + 12, y + 12, 5,
                     GREEN if info.get('is_available') else RED)
    disp.draw_text_pil(x + 23, y + 9, '总余额', LGRAY, size=10)
    # 右上角：当前峰/谷模式 + 切换倒计时
    mode_name = '梁文峰' if is_peak else '梁文谷'
    mode_clr = RED if is_peak else GREEN
    mode_txt = _fit(disp, f'{mode_name} {_fmt_cd(switch_sec)}', 10, 150)
    disp.draw_text_pil(x + w - 8 - disp.text_width_pil(mode_txt, 10), y + 9,
                       mode_txt, mode_clr, size=10)
    # 金额居中
    _, clr = _status(info)
    money = _fit(disp, f'{sym}{total}', 24, w - 24)
    disp.draw_text_pil(x + (w - disp.text_width_pil(money, 24)) // 2,
                       y + 26, money, clr, size=24)
    # 左下角：余额状态（着色）+ 充值/刷新信息
    st, st_clr = _status(info)
    st_w = disp.text_width_pil(st, 10)
    disp.draw_text_pil(x + 12, y + h - 11, st, st_clr, size=10)
    rest = (f' · 充值 {sym}{info.get("topped_up", "0.00")} · '
            f'刷新 {time.strftime("%H:%M", time.localtime(ts))}')
    disp.draw_text_pil(x + 12 + st_w, y + h - 11, rest, LGRAY, size=10)

    # ---------- 梁文峰（高峰）/ 梁文谷（空闲）模式卡 ----------
    cy = 108
    ai_ok = bool(ai and ai.get('ok'))
    _draw_mode_card(disp, 6, cy, _CARD_W, 48, '梁文峰模式', '高峰 x2',
                    is_peak, switch_sec, RED)
    _draw_mode_card(disp, 6 + _CARD_W + 8, cy, _CARD_W, 48, '梁文谷模式', '谷段 5折',
                    not is_peak, switch_sec, GREEN)

    # ---------- 今日 token 消耗曲线 ----------
    cy = 162
    disp.fill_round_rect(6, cy, W - 12, 72, 8, CARD)
    disp.draw_text_pil(18, cy + 6, '今日 Token 消耗', LGRAY, size=10)
    if ai_ok:
        hourly = ai.get('hourly') or []
        peak = max((t.get('total', 0) for t in hourly), default=0)
        if peak:
            tip = f'峰值 {_fmt_tokens(peak)}'
            disp.draw_text_pil(W - 14 - disp.text_width_pil(tip, 10),
                               cy + 6, tip, LGRAY, size=10)
    else:
        disp.draw_text_pil(W - 14 - disp.text_width_pil('代理离线', 10),
                           cy + 6, '代理离线', LGRAY, size=10)
    _draw_chart(disp, (ai.get('hourly') or []) if ai_ok else [])

    disp.flush()
