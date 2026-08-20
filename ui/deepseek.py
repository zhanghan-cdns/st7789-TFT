"""DeepSeek AI 监控页（AI 状态卡通卡 + 峰谷模式倒计时）

展示：
  - 状态卡：深色底 + 卡通人脸 + 光晕环，右侧大字状态文字。
    空闲=绿光晕+眯眯眼微笑，调用中=红光晕+忙碌表情+汗滴，离线=灰光晕+中性表情。
    忙碌时副行显示已调用时长。
  - 标题栏右侧：当前使用模型名（优先代理上报，其次 config 兜底）
  - 峰谷模式卡：梁文峰(高峰 x2) / 梁文谷(谷段 5折)，各带「进行中/后进入」切换倒计时

数据由 main 传入：
  ai:   service.deepseek.get_ai_state() 的返回 dict（None 表示加载中）
本模块只负责渲染，不发起任何网络请求。
"""
import datetime
import json
import math
import os
import time

from color import (
    BLACK, WHITE, RED, LGRAY,
)
from .dashboard import draw_page_frame

# 状态卡 / 模式卡 深色底
STATUS_BUSY_BG = 0x2082    # 暗红
STATUS_IDLE_BG = 0x08E2    # 暗绿
STATUS_OFF_BG  = 0x18E3    # 暗灰
MODE_PEAK_BG   = 0x2082    # 高峰卡底（暗红）
MODE_VALLEY_BG = 0x08E2    # 谷段卡底（暗绿）
# 人脸光晕环（中亮）
RING_BUSY      = 0x7904    # 中红
RING_IDLE      = 0x1A45    # 中绿
RING_OFF       = 0x4208    # 中灰
# 状态文字（浅色，柔和）
TXT_BUSY       = 0xFC51    # 浅红
TXT_IDLE       = 0x7F71    # 浅绿
TXT_OFF        = LGRAY
# 卡通人脸用色
FACE_YELLOW    = 0xFEAC    # 奶黄肤色
EYE_DARK       = BLACK     # 五官深色
BLUSH_PINK     = 0xFCB2    # 腮红
SWEAT_BLUE     = 0x2DFF    # 汗滴

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


def _fit(disp, text, size, max_w):
    """按像素宽度裁剪文本，超宽时尾部加省略号"""
    if disp.text_width_pil(text, size) <= max_w:
        return text
    while text and disp.text_width_pil(text + '\u2026', size) > max_w:
        text = text[:-1]
    return text + '\u2026'


def _traffic(ai):
    """状态卡：返回 (文字, 文字色)。ai 为 None 表示数据加载中。"""
    if ai is None:
        return '检测中', TXT_OFF
    if not ai.get('ok'):
        return '离线', TXT_OFF
    if ai.get('busy'):
        return '调用中', TXT_BUSY
    return '空闲', TXT_IDLE


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


# ---- 卡通人脸 ----

def _draw_arc(disp, cx, cy, r, a0, a1, color, thick=2):
    """折线画圆弧（屏幕坐标 y 向下：0°=右，90°=下）。thick 为线宽像素。"""
    n = max(int(abs(a1 - a0) // 4) + 1, 8)
    for k in range(thick):
        rr = r - k
        pts = []
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            pts.append((int(round(cx + rr * math.cos(a))),
                        int(round(cy + rr * math.sin(a)))))
        for i in range(n):
            disp.draw_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color)


def _draw_face(disp, cx, cy, r, mode):
    """卡通人脸。mode: 'idle'(绿·微笑) / 'busy'(红·忙碌) / 'off'(灰·中性)"""
    ring = {'busy': RING_BUSY, 'idle': RING_IDLE, 'off': RING_OFF}[mode]
    disp.fill_circle(cx, cy, r + 8, ring)   # 光晕环
    disp.fill_circle(cx, cy, r, FACE_YELLOW)

    if mode == 'idle':
        # 眯眯眼（◠）+ 微笑嘴 + 腮红
        for sx in (-1, 1):
            _draw_arc(disp, cx + sx * 11, cy - 7, 5, 200, 340, EYE_DARK)
        _draw_arc(disp, cx, cy + 8, 12, 15, 165, EYE_DARK)
        for sx in (-1, 1):
            disp.fill_circle(cx + sx * 17, cy + 6, 3, BLUSH_PINK)
    elif mode == 'busy':
        # 皱眉 + 圆睁眼 + 张嘴吐舌 + 汗滴
        for sx in (-1, 1):
            disp.draw_line(cx + sx * 15, cy - 17, cx + sx * 5, cy - 12, EYE_DARK)
            disp.draw_line(cx + sx * 15, cy - 16, cx + sx * 5, cy - 11, EYE_DARK)
            disp.fill_circle(cx + sx * 11, cy - 6, 3, EYE_DARK)
        disp.fill_circle(cx, cy + 13, 7, EYE_DARK)     # 张开的嘴
        disp.fill_circle(cx, cy + 16, 3, RED)          # 舌头
        # 额头右侧汗滴：跨过脸缘压到红色光晕上，更醒目
        disp.fill_circle(cx + 26, cy - 21, 5, SWEAT_BLUE)
        disp.draw_line(cx + 26, cy - 30, cx + 26, cy - 21, SWEAT_BLUE)
        disp.draw_line(cx + 25, cy - 29, cx + 25, cy - 21, SWEAT_BLUE)
    else:
        # 圆睁眼 + 中性嘴
        for sx in (-1, 1):
            disp.fill_circle(cx + sx * 11, cy - 6, 3, EYE_DARK)
        disp.draw_line(cx - 9, cy + 13, cx + 9, cy + 13, EYE_DARK)
        disp.draw_line(cx - 9, cy + 14, cx + 9, cy + 14, EYE_DARK)


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


def _draw_status_card(disp, ai):
    """AI 状态卡通卡：深色底 + 左侧人脸 + 右侧状态文字"""
    label, clr = _traffic(ai)
    if ai and ai.get('busy'):
        bg, mode = STATUS_BUSY_BG, 'busy'
    elif ai and ai.get('ok'):
        bg, mode = STATUS_IDLE_BG, 'idle'
    else:
        bg, mode = STATUS_OFF_BG, 'off'

    x, y, w, h = 6, 38, disp.width - 12, 132
    disp.fill_round_rect(x, y, w, h, 12, bg)

    # 左侧卡通人脸（光晕 + 肤色圆脸）
    cx, cy = x + 56, y + h // 2
    _draw_face(disp, cx, cy, 34, mode)

    # 右侧：大字状态 + 副行
    tx = cx + 34 + 24
    disp.draw_text_pil(tx, _ink_y(disp, label, 30, cy - 20), label, clr, size=30)
    if ai and ai.get('busy'):
        sec = int(ai.get('busy_sec') or 0)
        sub, sub_clr = f'已调用 {sec // 60:02d}:{sec % 60:02d}', WHITE
    elif ai is None:
        sub, sub_clr = '正在检测 AI 状态...', LGRAY
    elif not ai.get('ok'):
        sub, sub_clr = 'AI 服务未连接', LGRAY
    else:
        sub, sub_clr = '随时待命', WHITE
    disp.draw_text_pil(tx, _ink_y(disp, sub, 13, cy + 26), sub, sub_clr, size=13)


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


def draw_deepseek(disp, ai=None):
    """绘制 DeepSeek AI 监控页。

    ai:   get_ai_state() 返回值；None 表示 AI 状态加载中。
    """
    W = disp.width
    draw_page_frame(disp, 'DeepSeek 监控')
    _draw_model(disp, ai)
    _draw_status_card(disp, ai)

    # ---------- 峰谷模式卡 ----------
    is_peak, switch_sec = _peak_schedule()
    cy, ch = 178, 50
    cw = (W - 12 - 6) // 2
    _draw_mode_card(disp, 6, cy, cw, ch, '梁文峰', '高峰 x2', is_peak,
                    switch_sec, TXT_BUSY, MODE_PEAK_BG)
    _draw_mode_card(disp, 6 + cw + 6, cy, cw, ch, '梁文谷', '谷段 5折',
                    not is_peak, switch_sec, TXT_IDLE, MODE_VALLEY_BG)

    disp.flush()
