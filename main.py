"""ST7789 系统监控主程序

负责系统信息采集与主循环，调度 st7789_driver 驱动和 ui 渲染。
运行：python main.py
"""
import time
import os
import glob
import subprocess

from st7789_driver import ST7789
from ui import draw_dashboard


# ==================== 系统信息读取 ====================
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


_wifi_cache = None

def get_wifi_info():
    """返回 (ssid, signal_dbm, quality_pct)，失败时沿用上次缓存"""
    global _wifi_cache
    try:
        r = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=3)
        iface = None
        for line in r.stdout.split('\n'):
            if 'Interface' in line:
                iface = line.split('Interface')[-1].strip()
                break
        if not iface:
            for name in ['wlan0', 'wlp1s0', 'wlp2s0', 'wlp3s0']:
                if os.path.exists(f'/sys/class/net/{name}/wireless'):
                    iface = name
                    break
        if not iface:
            return _wifi_cache if _wifi_cache else ('', 0, 0)
        r = subprocess.run(['iw', 'dev', iface, 'link'], capture_output=True, text=True, timeout=3)
        ssid = ''
        signal = 0
        for line in r.stdout.split('\n'):
            s = line.strip()
            if s.startswith('SSID:'):
                ssid = s.split(':', 1)[1].strip()
            elif 'signal:' in s:
                signal = int(s.split(':')[1].strip().split()[0])
        if ssid:
            quality = max(0, min(100, round((signal + 90) * 100 / 60)))
            _wifi_cache = (ssid, signal, quality)
            return _wifi_cache
    except:
        pass
    if _wifi_cache is not None:
        return _wifi_cache
    return '', 0, 0


# ==================== 网络地址 ====================
def get_ip_address(iface):
    try:
        r = subprocess.run(['ip', '-4', 'addr', 'show', iface],
                         capture_output=True, text=True, timeout=3)
        for line in r.stdout.split('\n'):
            parts = line.strip().split()
            if len(parts) > 1 and parts[0] == 'inet':
                return parts[1].split('/')[0]
    except:
        pass
    return None


# ==================== 网络速度 ====================
def _detect_net_iface():
    for name in os.listdir('/sys/class/net'):
        if name == 'lo':
            continue
        try:
            with open(f'/sys/class/net/{name}/operstate') as f:
                if f.read().strip() == 'up':
                    return name
        except:
            continue
    return 'eth0'


def _read_net_bytes(iface):
    rx = tx = 0
    try:
        with open('/proc/net/dev') as f:
            for line in f:
                parts = line.split()
                if parts and parts[0].rstrip(':') == iface:
                    rx, tx = int(parts[1]), int(parts[9])
                    break
    except:
        pass
    return rx, tx


# ==================== 主程序 ====================
def main():
    print("ST7789 初始化中...")
    disp = ST7789()
    disp.init()
    print("初始化完成，启动系统监控")

    # 扫描 hwmon 设备（调试风扇）
    for d in glob.glob('/sys/class/hwmon/hwmon*'):
        try:
            name = open(f'{d}/name').read().strip()
            fans = glob.glob(f'{d}/fan*_input')
            if fans:
                print(f"  hwmon 设备: {name}  -> {fans}")
        except:
            pass

    net_iface = _detect_net_iface()
    prev_rx, prev_tx = _read_net_bytes(net_iface)
    net_ip = get_ip_address(net_iface)
    get_cpu_usage()  # 预热，建立 CPU 采样基准

    try:
        while True:
            cpu = get_cpu_usage()
            cpu_temp = get_cpu_temp()
            fan_val, fan_unit = get_fan_rpm()
            mem_used, mem_total, mem_pct = get_memory()
            wifi_ssid, wifi_dbm, wifi_q = get_wifi_info()

            rx, tx = _read_net_bytes(net_iface)
            net_down = rx - prev_rx
            net_up = tx - prev_tx
            prev_rx, prev_tx = rx, tx

            temp_s = f"{cpu_temp:.0f}C" if cpu_temp is not None else "N/A"
            print(f"CPU: {cpu:.1f}%  MEM: {mem_pct:.1f}%  TEMP: {temp_s}  "
                  f"FAN: {fan_val}{fan_unit or ''}  WiFi: {wifi_ssid} "
                  f"NET ↓{net_down//1024}K ↑{net_up//1024}K")
            draw_dashboard(disp, cpu, cpu_temp, fan_val, fan_unit,
                           mem_used, mem_total, mem_pct,
                           wifi_ssid, wifi_dbm, wifi_q,
                           net_down, net_up, net_ip)
            time.sleep(1)
    except KeyboardInterrupt:
        disp.close()
        print("程序退出")


if __name__ == "__main__":
    main()
