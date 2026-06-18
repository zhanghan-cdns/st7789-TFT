"""时钟页（第二屏）— 网页风格翻页时钟

时分秒三组、共 6 位独立翻页组件。每位数字分三层渲染：
  · 上遮罩（静态上半，显示新数字上半）
  · 下遮罩（静态下半，显示旧数字下半，直到叶片落下）
  · 翻转叶片（沿水平中轴竖向压缩/展开模拟 180° 翻转，叠加折叠内阴影）
数字变更时仅对变化位播放缓动翻页动画，并用驱动局部刷新保证流畅。
支持深色 / 浅色双主题（由 main 传入 theme 切换）。
"""
import os
import io
import json
import time as _time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

from color import BLACK, WHITE, CYAN, YELLOW, LGRAY, DGRAY, BLUE, ORANGE

# ── 布局常量 ──
CW, CH = 44, 84              # 单个翻页位宽高
R, SEAM = 6, 3              # 圆角半径 / 中缝（上下两半之间的黑缝）
TOP_H = (CH - SEAM) // 2     # 上半高
BOT_H = CH - TOP_H - SEAM    # 下半高
CARD_Y = 50                 # 翻页位顶部 y
SIZE = 74                   # 数字字号
SLOT_X = [6, 54, 114, 162, 222, 270]   # 6 位的 x（HH MM SS）
COLON_CX = [106, 214]       # 两个冒号中心 x（时|分、分|秒之间）
FRAMES = 7                  # 单次翻页帧数
SHADOW_MAX = 120            # 折叠阴影最大 alpha

# ── 双主题配色（RGB565）──
THEMES = {
    'dark': dict(bg=BLACK, hi=0x3186, lo=0x18E3, digit=WHITE, sep=CYAN,
                 date=LGRAY, lunar=YELLOW, hint=DGRAY, shadow=BLACK),
    'light': dict(bg=0xE71C, hi=0xFFFF, lo=0xCE79, digit=0x2104, sep=BLUE,
                  date=0x4208, lunar=ORANGE, hint=0x8410, shadow=BLACK),
}

_FONT_CACHE = {}
_MASK_CACHE = {}

# ── 卡片半透明 alpha（0~255）──
CARD_ALPHA = 140
_RR_CACHE = {}


def _rr_mask(w, h, r, fill=255):
    """缓存圆角矩形 'L' 遮罩（fill=alpha 0~255）"""
    key = (w, h, r, fill)
    if key not in _RR_CACHE:
        m = Image.new('L', (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=fill)
        _RR_CACHE[key] = m
    return _RR_CACHE[key]

# ── 背景图 ──
_BG_URL = 'http://oss.eleksmaker.com/nk/nk7d1.jpg'
_BG_CACHE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         'assets', 'clock_bg.raw')
_BG_RAW = None


def _load_bg(disp):
    """下载/缓存背景图，转 RGB565 后缓存到内存；失败返回 False"""
    global _BG_RAW
    if _BG_RAW is not None:
        return True
    W, H = disp.width, disp.height
    # 优先读本地缓存
    try:
        with open(_BG_CACHE, 'rb') as f:
            data = f.read()
            if len(data) == W * H * 2:
                _BG_RAW = data
                return True
    except OSError:
        pass
    # 下载
    try:
        resp = urllib.request.urlopen(_BG_URL, timeout=10)
        img = Image.open(io.BytesIO(resp.read())).convert('RGB')
        if img.size != (W, H):
            img = img.resize((W, H), Image.LANCZOS)
        raw = bytearray(W * H * 2)
        i = 0
        for r, g, b in img.getdata():
            rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            raw[i] = (rgb565 >> 8) & 0xFF
            raw[i + 1] = rgb565 & 0xFF
            i += 2
        _BG_RAW = bytes(raw)
        try:
            with open(_BG_CACHE, 'wb') as f:
                f.write(_BG_RAW)
        except OSError:
            pass
        return True
    except Exception as e:
        print(f"[clock] bg download failed: {e}")
        return False


def _font(size):
    """按字号加载字体（读 config.json 的 font_paths，失败回退默认）"""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    paths = []
    try:
        cfg = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'config.json')
        with open(cfg, 'r', encoding='utf-8') as f:
            paths = json.load(f).get('font_paths', [])
    except (IOError, OSError, ValueError):
        pass
    font = None
    for p in paths:
        try:
            font = ImageFont.truetype(p, size)
            break
        except (IOError, OSError):
            continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def _digit_halves(ch):
    """返回数字 ch 居中绘制后裁出的 (上半掩码, 下半掩码) PIL 'L' 图，带缓存"""
    if ch in _MASK_CACHE:
        return _MASK_CACHE[ch]
    img = Image.new('L', (CW, CH), 0)
    d = ImageDraw.Draw(img)
    font = _font(SIZE)
    bbox = d.textbbox((0, 0), ch, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    px = (CW - tw) // 2 - bbox[0]
    py = (CH - th) // 2 - bbox[1]
    d.text((px, py), ch, font=font, fill=255)
    top = img.crop((0, 0, CW, TOP_H))
    bot = img.crop((0, TOP_H + SEAM, CW, CH))
    _MASK_CACHE[ch] = (top, bot)
    return top, bot


def _restore_card(disp, x, th):
    """将单个翻页位恢复为纯背景（背景图或纯色），避免动画累积透明度"""
    if _BG_RAW is not None:
        stride = disp.width * 2
        base = CARD_Y * stride + x * 2
        for row in range(CH):
            off = base + row * stride
            disp.fbuf[off:off + CW * 2] = _BG_RAW[off:off + CW * 2]
    else:
        disp.fill_rect(x, CARD_Y, CW, CH, th['bg'])


def _card_bg(disp, x, th, alpha=255):
    """半透明翻页位底卡：blit_mask 叠加圆角遮罩，中缝留底色"""
    mt = _rr_mask(CW, TOP_H, R, alpha)
    mb = _rr_mask(CW, BOT_H, R, alpha)
    disp.blit_mask(x, CARD_Y, mt, th['hi'])
    disp.blit_mask(x, CARD_Y + TOP_H + SEAM, mb, th['lo'])


def _draw_static(disp, x, ch, th, alpha=255):
    """静态绘制一个完整数字位（无动画）"""
    _card_bg(disp, x, th, alpha)
    top, bot = _digit_halves(ch)
    disp.blit_mask(x, CARD_Y, top, th['digit'])
    disp.blit_mask(x, CARD_Y + TOP_H + SEAM, bot, th['digit'])


def _ease(t):
    """easeInOutCubic：起止平滑、中段加速，带轻微回弹观感"""
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def _leaf(disp, x, y, h, half_mask, panel, th, alpha):
    """绘制一片翻转叶片：压缩后的面板 + 数字半，叠加折叠内阴影"""
    if h < 1:
        return
    disp.fill_rect(x, y, CW, h, panel)
    dm = half_mask.resize((CW, h), Image.BILINEAR)
    disp.blit_mask(x, y, dm, th['digit'])
    if alpha > 0:
        disp.blit_mask(x, y, Image.new('L', (CW, h), alpha), th['shadow'])


def _compose(disp, x, old_ch, new_ch, t, th, alpha=255):
    """合成一帧：静态上半=新、静态下半=旧，叶片按相位翻转"""
    _restore_card(disp, x, th)
    _card_bg(disp, x, th, alpha)
    n_top, n_bot = _digit_halves(new_ch)
    o_top, o_bot = _digit_halves(old_ch)
    disp.blit_mask(x, CARD_Y, n_top, th['digit'])                 # 上半：新
    disp.blit_mask(x, CARD_Y + TOP_H + SEAM, o_bot, th['digit'])  # 下半：旧
    if t < 0.5:
        # 相位 1：旧上半沿中轴向下折叠（高度 1→0，下沿固定在中轴）
        p = t / 0.5
        h = max(0, round(TOP_H * (1 - p)))
        _leaf(disp, x, CARD_Y + TOP_H - h, h, o_top, th['hi'], th,
              int(SHADOW_MAX * p))
    else:
        # 相位 2：新下半沿中轴向下展开（高度 0→1，上沿固定在中轴）
        p = (t - 0.5) / 0.5
        h = max(0, round(BOT_H * p))
        _leaf(disp, x, CARD_Y + TOP_H + SEAM, h, n_bot, th['lo'], th,
              int(SHADOW_MAX * (1 - p)))


def draw_clock(disp, time_str, date_str, week_str, lunar_str, theme='dark'):
    """绘制翻页时钟页

    参数：
      time_str — "HH:MM:SS"；date_str/week_str/lunar_str — 日期/星期/农历
      theme    — 'dark' 或 'light'
    """
    W, H = disp.width, disp.height
    th = THEMES.get(theme, THEMES['dark'])

    parts = (time_str.split(':') + ['00', '00', '00'])[:3]
    digits = ''.join(p.zfill(2)[:2] for p in parts)  # 6 位 HHMMSS

    prev = getattr(draw_clock, '_prev', None)
    prev_theme = getattr(draw_clock, '_theme', None)
    draw_clock._prev = digits
    draw_clock._theme = theme
    # 仅当上次有记录且主题未变时才做翻页动画
    animate = prev is not None and prev_theme == theme and len(prev) == 6

    # ── 全屏静态底：背景 + 冒号 + 日期/农历 + 6 位数字（动画时数字先画旧值）──
    if _load_bg(disp):
        disp.fbuf[:] = _BG_RAW
    else:
        disp.fill_screen(th['bg'])
    if int(digits[4:6]) % 2 == 0:                    # 冒号每秒闪烁
        cy = CARD_Y + CH // 2
        for cxc in COLON_CX:
            disp.fill_circle(cxc, cy - 15, 4, th['sep'])
            disp.fill_circle(cxc, cy + 15, 4, th['sep'])

    date_line = f"{date_str}  {week_str}"
    dw, dh = disp.text_size_pil(date_line, 18)
    lw, _ = disp.text_size_pil(lunar_str, 20)
    y = CARD_Y + CH + 12
    disp.draw_text_pil((W - dw) // 2, y, date_line, th['date'], size=18)
    y += dh + 10
    disp.draw_text_pil((W - lw) // 2, y, lunar_str, th['lunar'], size=20)
    hint = "Enter: theme   \u2190 \u2192 back"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil((W - hw) // 2, H - 14, hint, th['hint'], size=10)

    base = prev if animate else digits
    for i, xx in enumerate(SLOT_X):
        _draw_static(disp, xx, base[i], th, alpha=CARD_ALPHA)
    disp.flush()

    if not animate:
        return
    changed = [i for i in range(6) if prev[i] != digits[i]]
    if not changed:
        return

    # ── 翻页动画：仅重绘变化位，局部刷新其外接矩形 ──
    minx = min(SLOT_X[i] for i in changed)
    maxx = max(SLOT_X[i] + CW for i in changed)
    for f in range(1, FRAMES + 1):
        t = _ease(f / FRAMES)
        for i in changed:
            _compose(disp, SLOT_X[i], prev[i], digits[i], t, th, alpha=CARD_ALPHA)
        disp.flush_rect(minx, CARD_Y, maxx - minx, CH)
        _time.sleep(0.012)
    # 收尾：还原圆角静态新数字
    for i in changed:
        _restore_card(disp, SLOT_X[i], th)
        _draw_static(disp, SLOT_X[i], digits[i], th, alpha=CARD_ALPHA)
    disp.flush_rect(minx, CARD_Y, maxx - minx, CH)
