"""菜单图标加载（assets/*.svg → alpha 蒙版，带缓存）

把 assets 目录里的 SVG 图标栅格化为指定尺寸的 alpha 蒙版供 blit_mask 着色绘制。
栅格化结果按 (页面, 尺寸) 缓存，首帧渲染后即常驻内存，后续零开销。
设备端无需 cairo/SVG 系统库（见 svg_raster）。
"""
import os

from .svg_raster import rasterize_svg

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')

# 菜单页标识 → 对应 SVG 文件名
_ICON_FILES = {
    'dashboard': 'systemMonitoring.svg',
    'clock': 'time.svg',
    'services': 'systemd.svg',
    'music': 'music.svg',
    'camera': 'camera.svg',
    'shutdown': 'poweroff.svg',
    'update': 'update.svg',
}

_cache = {}


def get_icon(page, size):
    """返回 page 对应图标的 alpha 蒙版(PIL 'L')，无图标或渲染失败返回 None"""
    name = _ICON_FILES.get(page)
    if not name:
        return None
    key = (page, size)
    if key not in _cache:
        path = os.path.join(_ASSETS, name)
        try:
            _cache[key] = rasterize_svg(path, size)
        except Exception:
            _cache[key] = None
    return _cache[key]
