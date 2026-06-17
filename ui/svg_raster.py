"""纯 Python SVG 路径栅格化（仅依赖 Pillow）

把简单的单色 SVG（仅 <path>，含 viewBox）渲染为 alpha 蒙版(PIL 'L')。
支持 M/L/H/V/C/S/Q/T/A/Z（含小写相对指令），even-odd 填充，超采样抗锯齿。
设备端无需 cairo/SVG 等系统库，开发机与设备端表现一致。
"""
import math
import re

from PIL import Image, ImageChops, ImageDraw

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")
_VIEWBOX = re.compile(r'viewBox\s*=\s*"([^"]+)"')
_PATH_D = re.compile(r'<path[^>]*\bd\s*=\s*"([^"]+)"', re.S)


def _cubic(p0, p1, p2, p3, n=14):
    out = []
    for k in range(1, n + 1):
        t = k / n; m = 1 - t
        out.append((m*m*m*p0[0] + 3*m*m*t*p1[0] + 3*m*t*t*p2[0] + t*t*t*p3[0],
                    m*m*m*p0[1] + 3*m*m*t*p1[1] + 3*m*t*t*p2[1] + t*t*t*p3[1]))
    return out


def _quad(p0, p1, p2, n=12):
    out = []
    for k in range(1, n + 1):
        t = k / n; m = 1 - t
        out.append((m*m*p0[0] + 2*m*t*p1[0] + t*t*p2[0],
                    m*m*p0[1] + 2*m*t*p1[1] + t*t*p2[1]))
    return out


def _arc(x0, y0, rx, ry, phi, large, sweep, x1, y1):
    if rx == 0 or ry == 0 or (x0 == x1 and y0 == y1):
        return [(x1, y1)]
    phi = math.radians(phi)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    xp = cp * dx + sp * dy; yp = -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = xp*xp/(rx*rx) + yp*yp/(ry*ry)
    if lam > 1:
        s = math.sqrt(lam); rx *= s; ry *= s
    den = rx*rx*yp*yp + ry*ry*xp*xp
    num = rx*rx*ry*ry - den
    co = math.sqrt(max(0, num / den)) if den else 0
    if large == sweep:
        co = -co
    cxp = co * rx * yp / ry; cyp = -co * ry * xp / rx
    cx = cp * cxp - sp * cyp + (x0 + x1) / 2
    cy = sp * cxp + cp * cyp + (y0 + y1) / 2

    def ang(ux, uy, vx, vy):
        d = math.sqrt((ux*ux + uy*uy) * (vx*vx + vy*vy))
        c = max(-1, min(1, (ux*vx + uy*vy) / d)) if d else 1
        a = math.acos(c)
        return -a if ux*vy - uy*vx < 0 else a

    th1 = ang(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    dth = ang((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    if sweep and dth < 0:
        dth += 2 * math.pi
    n = max(2, int(abs(dth) / (math.pi / 12)) + 1)
    out = []
    for k in range(1, n + 1):
        th = th1 + dth * k / n
        out.append((cp*rx*math.cos(th) - sp*ry*math.sin(th) + cx,
                    sp*rx*math.cos(th) + cp*ry*math.sin(th) + cy))
    return out


def _parse_d(d):
    """解析 path 的 d 属性为若干闭合子路径（每个是点列表）"""
    toks = _TOKEN.findall(d)
    i, n = 0, len(toks)
    subs, cur = [], []
    x = y = sx = sy = lcx = lcy = lqx = lqy = 0.0
    cmd = prev = ''

    def f():
        nonlocal i
        v = float(toks[i]); i += 1; return v

    while i < n:
        if toks[i][0].isalpha():
            cmd = toks[i]; i += 1
            if cmd in 'Zz':
                if cur:
                    cur.append((sx, sy)); subs.append(cur); cur = []
                x, y = sx, sy; prev = 'Z'
                continue
        C = cmd.upper(); rel = cmd.islower()
        if C == 'M':
            x = (x if rel else 0) + f(); y = (y if rel else 0) + f()
            sx, sy = x, y
            if cur:
                subs.append(cur)
            cur = [(x, y)]; cmd = 'l' if rel else 'L'
        elif C == 'L':
            x = (x if rel else 0) + f(); y = (y if rel else 0) + f(); cur.append((x, y))
        elif C == 'H':
            x = (x if rel else 0) + f(); cur.append((x, y))
        elif C == 'V':
            y = (y if rel else 0) + f(); cur.append((x, y))
        elif C in ('C', 'S'):
            if C == 'C':
                x1 = (x if rel else 0) + f(); y1 = (y if rel else 0) + f()
            else:
                x1, y1 = (2*x - lcx, 2*y - lcy) if prev in 'CS' else (x, y)
            x2 = (x if rel else 0) + f(); y2 = (y if rel else 0) + f()
            nx = (x if rel else 0) + f(); ny = (y if rel else 0) + f()
            cur += _cubic((x, y), (x1, y1), (x2, y2), (nx, ny))
            lcx, lcy = x2, y2; x, y = nx, ny
        elif C in ('Q', 'T'):
            if C == 'Q':
                x1 = (x if rel else 0) + f(); y1 = (y if rel else 0) + f()
            else:
                x1, y1 = (2*x - lqx, 2*y - lqy) if prev in 'QT' else (x, y)
            nx = (x if rel else 0) + f(); ny = (y if rel else 0) + f()
            cur += _quad((x, y), (x1, y1), (nx, ny))
            lqx, lqy = x1, y1; x, y = nx, ny
        elif C == 'A':
            rx = f(); ry = f(); rot = f(); la = int(f()); sw = int(f())
            nx = (x if rel else 0) + f(); ny = (y if rel else 0) + f()
            cur += _arc(x, y, rx, ry, rot, la, sw, nx, ny); x, y = nx, ny
        prev = C
    if cur:
        subs.append(cur)
    return subs


def rasterize_svg(path, size, ss=4):
    """读取 SVG 文件，返回 size×size 的 alpha 蒙版(PIL 'L'，0~255)"""
    with open(path, 'r', encoding='utf-8') as fh:
        data = fh.read()
    m = _VIEWBOX.search(data)
    vx, vy, vw, vh = ([float(v) for v in re.split(r'[ ,]+', m.group(1).strip())]
                      if m else [0, 0, 1024, 1024])
    W = H = max(1, size * ss)
    sxr, syr = W / vw, H / vh
    overall = Image.new('1', (W, H), 0)
    for dm in _PATH_D.findall(data):
        pmask = Image.new('1', (W, H), 0)
        for sub in _parse_d(dm):
            if len(sub) < 3:
                continue
            poly = Image.new('1', (W, H), 0)
            ImageDraw.Draw(poly).polygon(
                [((px - vx) * sxr, (py - vy) * syr) for px, py in sub], fill=1)
            pmask = ImageChops.logical_xor(pmask, poly)
        overall = ImageChops.logical_or(overall, pmask)
    return overall.convert('L').resize((size, size), Image.LANCZOS)
