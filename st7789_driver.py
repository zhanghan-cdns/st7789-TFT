"""ST7789 SPI 显示屏驱动（鲁班猫3 / RK3576）

只负责屏幕点亮与底层驱动：硬件控制 + 帧缓冲绘图原语。
颜色常量见 color 模块，位图字体见 font 模块。
硬件参数（SPI/GPIO 引脚等）见 config.json。
"""
import json
import os
import spidev
import gpiod
import time

from font import font_glyph

_CONFIG = None

def load_config(path=None):
    """加载 config.json，返回配置字典"""
    global _CONFIG
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(path, "r") as f:
        _CONFIG = json.load(f)
    return _CONFIG

def get_config(path=None):
    """获取配置，未加载则自动加载"""
    global _CONFIG
    if _CONFIG is None:
        load_config(path)
    return _CONFIG


class ST7789:
    """ST7789 显示屏驱动：硬件控制 + 帧缓冲 + 字体绘制"""

    def __init__(self, config_path=None, **kwargs):
        cfg = get_config(config_path)
        dpy = cfg["display"]
        spi = cfg["spi"]
        gpio = cfg["gpio"]

        # kwargs 可覆盖 config.json
        self.width = kwargs.get("width", dpy["width"])
        self.height = kwargs.get("height", dpy["height"])
        self.x_offset = kwargs.get("x_offset", dpy["x_offset"])
        self.y_offset = kwargs.get("y_offset", dpy["y_offset"])
        spi_bus = kwargs.get("spi_bus", spi["bus"])
        spi_dev = kwargs.get("spi_dev", spi["device"])
        speed_hz = kwargs.get("speed_hz", spi["speed_hz"])
        spi_mode = kwargs.get("spi_mode", spi["mode"])
        rst_chip = kwargs.get("rst_chip", gpio["rst_chip"])
        rst_pin = kwargs.get("rst_pin", gpio["rst_pin"])
        dc_chip = kwargs.get("dc_chip", gpio["dc_chip"])
        dc_pin = kwargs.get("dc_pin", gpio["dc_pin"])

        # SPI 初始化
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_dev)
        self.spi.mode = spi_mode
        self.spi.max_speed_hz = speed_hz

        # GPIO 初始化（CS 由硬件控制，这里只需 RES 和 DC）
        self._rst_chip = gpiod.Chip(rst_chip)
        self._dc_chip = gpiod.Chip(dc_chip)
        self._rst_line = self._rst_chip.get_line(rst_pin)
        self._dc_line = self._dc_chip.get_line(dc_pin)
        self._rst_line.request(consumer="st7789", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])
        self._dc_line.request(consumer="st7789", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])

        # 帧缓冲
        self.fbuf = bytearray(self.width * self.height * 2)

    # ==================== 底层函数 ====================
    def _spi_write(self, data):
        """SPI 发送数据；CS 由 spidev 硬件自动控制，writebytes2 自动分片大缓冲"""
        self.spi.writebytes2(data)

    def _cmd(self, cmd):
        """发送命令"""
        self._dc_line.set_value(0)
        self._spi_write([cmd])

    def _data(self, data):
        """发送数据"""
        self._dc_line.set_value(1)
        if isinstance(data, list):
            self._spi_write(data)
        else:
            self._spi_write([data])

    def _reset(self):
        """屏幕复位"""
        self._rst_line.set_value(0)
        time.sleep(0.1)
        self._rst_line.set_value(1)
        time.sleep(0.15)

    # ==================== ST7789 初始化 ====================
    def init(self):
        self._reset()
        self._cmd(0x36)
        self._data(0x60)   # 横屏 320x240：MX+MV（修正左右镜像）
        self._cmd(0x3A)
        self._data(0x55)
        self._cmd(0xB2)
        self._data([0x0C, 0x0C, 0x00, 0x33, 0x33])
        self._cmd(0xB7)
        self._data(0x35)
        self._cmd(0xBB)
        self._data(0x19)
        self._cmd(0xC0)
        self._data(0x2C)
        self._cmd(0xC2)
        self._data(0x01)
        self._cmd(0xC3)
        self._data(0x12)
        self._cmd(0xC4)
        self._data(0x20)
        self._cmd(0xC6)
        self._data(0x0F)
        self._cmd(0xD0)
        self._data([0xA4, 0xA1])
        self._cmd(0xE0)
        self._data([0xD0,0x08,0x11,0x08,0x0C,0x15,0x39,0x44,0x4D,0x18,0x12,0x17,0x1A,0x19])
        self._cmd(0xE1)
        self._data([0xD0,0x08,0x10,0x08,0x06,0x06,0x39,0x44,0x4C,0x17,0x14,0x15,0x18,0x19])
        self._cmd(0x21)
        self._cmd(0x11)
        time.sleep(0.15)
        self._cmd(0x29)

    # ==================== 窗口 / 清屏 ====================
    def set_window(self, x0, y0, x1, y1):
        """设置显示区域，自动加偏移"""
        x0 += self.x_offset; x1 += self.x_offset
        y0 += self.y_offset; y1 += self.y_offset
        self._cmd(0x2A)
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(0x2B)
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._cmd(0x2C)

    def clear(self, color):
        """直接清屏，color: 16位RGB颜色"""
        self.set_window(0, 0, self.width - 1, self.height - 1)
        high = (color >> 8) & 0xFF
        low = color & 0xFF
        buf = bytearray([high, low]) * (self.width * self.height)
        self._dc_line.set_value(1)   # 关键：进入数据模式，否则像素会被当成命令丢弃
        self._spi_write(buf)

    # ==================== 帧缓冲绘图 ====================
    def draw_pixel(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 2
            self.fbuf[i]   = (color >> 8) & 0xFF
            self.fbuf[i+1] = color & 0xFF

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x); y0 = max(0, y)
        x1 = min(self.width, x + w); y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        row = bytearray([hi, lo]) * (x1 - x0)
        stride = self.width * 2
        off = y0 * stride + x0 * 2
        for py in range(y0, y1):
            self.fbuf[off:off + len(row)] = row
            off += stride

    def fill_round_rect(self, x, y, w, h, r, color):
        """填充圆角矩形，r 为圆角半径"""
        r = min(r, w // 2, h // 2)
        if r <= 0:
            self.fill_rect(x, y, w, h, color)
            return
        # 中间主体
        self.fill_rect(x, y + r, w, h - 2 * r, color)
        # 上下圆角带
        for dy in range(r):
            dx = r - int((r * r - (r - dy) * (r - dy)) ** 0.5)
            self.fill_rect(x + dx, y + dy, w - 2 * dx, 1, color)
            self.fill_rect(x + dx, y + h - 1 - dy, w - 2 * dx, 1, color)

    def fill_circle(self, cx, cy, r, color):
        """填充圆，中点圆算法"""
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        pixel = bytearray([hi, lo])
        stride = self.width * 2
        for y in range(-r, r + 1):
            dy = abs(y)
            if dy > r:
                continue
            dx = int((r * r - dy * dy) ** 0.5)
            x0 = max(0, cx - dx)
            x1 = min(self.width, cx + dx + 1)
            if x0 >= x1:
                continue
            py = cy + y
            if py < 0 or py >= self.height:
                continue
            off = py * stride + x0 * 2
            self.fbuf[off:off + (x1 - x0) * 2] = pixel * (x1 - x0)

    def blit_mask(self, x, y, mask, color):
        """将 alpha 蒙版(PIL 'L', 0~255)按 color 着色并 alpha 混合到帧缓冲。

        用于绘制图标：mask 非零处用 color 与底色按 alpha 混合，实现抗锯齿。
        """
        fr = ((color >> 11) & 0x1F) << 3
        fg = ((color >> 5) & 0x3F) << 2
        fb = (color & 0x1F) << 3
        px = mask.load()
        mw, mh = mask.size
        stride = self.width * 2
        for py in range(mh):
            iy = y + py
            if iy < 0 or iy >= self.height:
                continue
            for pxx in range(mw):
                a = px[pxx, py]
                if a == 0:
                    continue
                ix = x + pxx
                if ix < 0 or ix >= self.width:
                    continue
                off = iy * stride + ix * 2
                if a >= 255:
                    self.fbuf[off] = (color >> 8) & 0xFF
                    self.fbuf[off + 1] = color & 0xFF
                    continue
                bg = (self.fbuf[off] << 8) | self.fbuf[off + 1]
                br = ((bg >> 11) & 0x1F) << 3
                bgc = ((bg >> 5) & 0x3F) << 2
                bb = (bg & 0x1F) << 3
                inv = 255 - a
                r = (fr * a + br * inv) // 255
                g = (fg * a + bgc * inv) // 255
                b = (fb * a + bb * inv) // 255
                c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                self.fbuf[off] = (c >> 8) & 0xFF
                self.fbuf[off + 1] = c & 0xFF

    def draw_line(self, x0, y0, x1, y1, color):
        """Bresenham 画线"""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.draw_pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = err * 2
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def fill_screen(self, color):
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        pixel = bytearray([hi, lo])
        self.fbuf[:] = pixel * (self.width * self.height)

    def flush(self):
        """将帧缓冲整屏刷新到屏幕"""
        self.set_window(0, 0, self.width - 1, self.height - 1)
        self._dc_line.set_value(1)
        self._spi_write(self.fbuf)

    def flush_rect(self, x, y, w, h):
        """仅刷新指定矩形区域到屏幕（局部动画用，减少 SPI 传输量、保证流畅）"""
        x0 = max(0, x); y0 = max(0, y)
        x1 = min(self.width, x + w); y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        self.set_window(x0, y0, x1 - 1, y1 - 1)
        stride = self.width * 2
        row_bytes = (x1 - x0) * 2
        buf = bytearray(row_bytes * (y1 - y0))
        pos = 0
        for py in range(y0, y1):
            off = py * stride + x0 * 2
            buf[pos:pos + row_bytes] = self.fbuf[off:off + row_bytes]
            pos += row_bytes
        self._dc_line.set_value(1)
        self._spi_write(buf)

    # ==================== 字体绘制 ====================
    def draw_char(self, x, y, ch, color, scale=1):
        glyph = font_glyph(ch)
        if glyph is None:
            return
        for col in range(5):
            bits = glyph[col]
            for row in range(8):
                if bits & (1 << row):
                    for sx in range(scale):
                        for sy in range(scale):
                            self.draw_pixel(x + col*scale + sx, y + row*scale + sy, color)

    def draw_text(self, x, y, text, color, scale=1):
        for i, ch in enumerate(text):
            self.draw_char(x + i * 6 * scale, y, ch, color, scale)

    _FONT_CACHE = {}

    def _pil_font(self, size, font_path=None):
        key = (size, font_path)
        if key not in self._FONT_CACHE:
            try:
                from PIL import ImageFont
            except ImportError:
                raise ImportError("需要 Pillow: pip install Pillow")
            # 显式字体优先；加载失败不再直接抛异常（否则会让服务崩溃重启），
            # 而是回退到 assets 内置字体 → config 候选字体 → 默认字体。
            if font_path:
                try:
                    self._FONT_CACHE[key] = ImageFont.truetype(font_path, size)
                except (IOError, OSError) as e:
                    print(f"[font] 加载失败 {font_path}: {e}，回退候选字体")
            if key not in self._FONT_CACHE:
                # 优先使用 assets 内置字体（阿里巴巴普惠体 Heavy）
                builtin = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'assets', 'AlibabaPuHuiTi-3-105-Heavy.ttf')
                builtin_candidates = [builtin] if os.path.exists(builtin) else []
                candidates = builtin_candidates + get_config().get("font_paths", [])
                for p in candidates:
                    try:
                        self._FONT_CACHE[key] = ImageFont.truetype(p, size)
                        break
                    except (IOError, OSError):
                        continue 
            if key not in self._FONT_CACHE:
                self._FONT_CACHE[key] = ImageFont.load_default()
        return self._FONT_CACHE[key]

    def text_size_pil(self, text, size=16, font_path=None):
        font = self._pil_font(size, font_path)
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def text_width_pil(self, text, size=16, font_path=None):
        w, _ = self.text_size_pil(text, size, font_path)
        return w

    def draw_text_pil(self, x, y, text, color, size=16, font_path=None, clip=None):
        """绘制文字；clip=(x0,y0,x1,y1) 时仅在该矩形内绘制（用于滑动动画裁剪）"""
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            raise ImportError("需要 Pillow: pip install Pillow")
        font = self._pil_font(size, font_path)
        bbox = font.getbbox(text)
        tw, th = bbox[2], bbox[3]
        if tw <= 0 or th <= 0:
            return
        img = Image.new("1", (tw, th), 0)
        draw = ImageDraw.Draw(img)
        draw.text((-bbox[0], -bbox[1]), text, font=font, fill=1)

        # 裁剪边界（默认整屏）
        cx0, cy0, cx1, cy1 = (clip if clip is not None
                              else (0, 0, self.width, self.height))

        hi = (color >> 8) & 0xFF
        lo = color & 0xFF

        # 优先 numpy 向量化写帧缓冲：比逐像素 getpixel 快约 30 倍，
        # 解决设备端大字体/多段文字渲染卡顿。无 numpy 时回退纯 Python。
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is not None:
            try:
                mask = np.array(img, dtype=bool)
                dx0 = max(x, 0, cx0); dy0 = max(y, 0, cy0)
                dx1 = min(x + tw, self.width, cx1)
                dy1 = min(y + th, self.height, cy1)
                if dx0 < dx1 and dy0 < dy1:
                    sub = mask[dy0 - y:dy1 - y, dx0 - x:dx1 - x]
                    fb = np.frombuffer(self.fbuf, dtype=np.uint8).reshape(
                        self.height, self.width, 2)
                    fb[dy0:dy1, dx0:dx1][sub] = (hi, lo)
                return
            except Exception:
                pass  # 任何异常都回退逐像素，绝不让渲染崩溃

        pixel = bytearray([hi, lo])
        stride = self.width * 2
        for py in range(th):
            iy = y + py
            if iy < 0 or iy >= self.height or iy < cy0 or iy >= cy1:
                continue
            for px in range(tw):
                ix = x + px
                if ix < 0 or ix >= self.width or ix < cx0 or ix >= cx1:
                    continue
                if img.getpixel((px, py)):
                    off = iy * stride + ix * 2
                    self.fbuf[off:off+2] = pixel

    # ==================== 资源释放 ====================
    def close(self):
        self._dc_line.release()
        self._rst_line.release()
        self.spi.close()
        self._dc_chip.close()
        self._rst_chip.close()
