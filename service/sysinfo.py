"""系统信息读取：CPU 使用率/温度、风扇转速、内存、磁盘、运行时间。

均读取 /proc 与 /sys，毫秒级返回，适合主循环每秒调用。
"""
import glob
import os


def _read_cpu_times():
    with open('/proc/stat', 'r') as f:
        parts = f.readline().split()
    return [int(x) for x in parts[1:]]


_prev_cpu = None  # 上次 /proc/stat 快照 (total, idle)


def get_cpu_usage():
    """基于两次调用间的增量计算 CPU 使用率，覆盖整个采样周期。

    首次调用无基准返回 0.0，之后每轮用相邻两次的差值计算，
    使测量窗口覆盖整个循环（含绘制/子进程），避免短窗口读到假 0。
    """
    global _prev_cpu
    t = _read_cpu_times()
    total, idle = sum(t), t[3]
    prev = _prev_cpu
    _prev_cpu = (total, idle)
    if prev is None:
        return 0.0
    d_total = total - prev[0]
    d_idle = idle - prev[1]
    if d_total <= 0:
        return 0.0
    return round(100.0 * (1 - d_idle / d_total), 1)


def get_cpu_temp():
    """返回 CPU 温度（摄氏度，float），读取失败返回 None"""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return int(f.read().strip()) / 1000.0
    except:
        return None


def get_fan_rpm():
    """返回 (rpm_or_pwm, unit)，unit 为 'RPM' 或 '%'，失败返回 (None, None)"""
    # 优先读有转速传感器的
    for path in glob.glob('/sys/class/hwmon/hwmon*/fan*_input'):
        try:
            val = int(open(path).read().strip())
            if val > 0:
                return val, 'RPM'
        except:
            pass
    # 退回到 PWM 占空比
    for path in glob.glob('/sys/class/hwmon/hwmon*/pwm1'):
        try:
            val = int(open(path).read().strip())
            pct = val * 100 // 255
            return pct, '%'
        except:
            pass
    return None, None


def get_memory():
    """返回 (used_mb, total_mb, pct)"""
    mem = {}
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            if ':' in line:
                k, v = line.split(':', 1)
                mem[k.strip()] = int(v.strip().split()[0])
    total = mem.get('MemTotal', 1)
    avail = mem.get('MemAvailable', mem.get('MemFree', 0) + mem.get('Buffers', 0) + mem.get('Cached', 0))
    used = total - avail
    pct = round(100.0 * used / total, 1)
    return round(used / 1024, 1), round(total / 1024, 1), pct


def get_disk_usage():
    """返回 (used_gb, total_gb, pct)"""
    try:
        s = os.statvfs('/')
        total = s.f_frsize * s.f_blocks
        free = s.f_frsize * s.f_bavail
        used = total - free
        pct = round(100.0 * used / total, 1) if total else 0
        return round(used / (1024**3), 1), round(total / (1024**3), 1), pct
    except Exception:
        return 0, 0, 0


def get_uptime():
    """返回运行时间字符串，如 "2天 3小时 15分" """
    try:
        with open('/proc/uptime', 'r') as f:
            secs = int(float(f.read().split()[0]))
    except Exception:
        return '--'
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m = secs // 60
    parts = []
    if d:
        parts.append(f'{d}天')
    if h:
        parts.append(f'{h}小时')
    parts.append(f'{m}分')
    return ''.join(parts)
