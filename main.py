"""ST7789 系统监控主程序

负责系统信息采集与主循环，调度 st7789_driver 驱动和 ui 渲染。
运行：python main.py
"""
import time
import os
import subprocess

from st7789_driver import ST7789
from ui import draw_dashboard


# ==================== 系统信息读取 ====================
def _read_cpu_times():
    with open('/proc/stat', 'r') as f:
        parts = f.readline().split()
    return [int(x) for x in parts[1:]]


def get_cpu_usage():
    """返回 CPU 总使用率百分比"""
    t1 = _read_cpu_times()
    time.sleep(0.2)
    t2 = _read_cpu_times()
    idle1 = t1[3]; total1 = sum(t1)
    idle2 = t2[3]; total2 = sum(t2)
    d_idle = idle2 - idle1
    d_total = total2 - total1
    if d_total == 0:
        return 0.0
    return round(100.0 * (1 - d_idle / d_total), 1)


def get_cpu_temp():
    """返回 CPU 温度字符串，如 '45C'，读取失败返回 'N/A'"""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return f"{int(f.read().strip())/1000:.0f}C"
    except:
        return "N/A"


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


def get_wifi_info():
    """返回 (ssid, signal_dbm, quality_pct)，未连接返回 ('', 0, 0)"""
    try:
        # 方法1: nmcli (Ubuntu 默认 NetworkManager)
        r = subprocess.run(
            ['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL', 'dev', 'wifi', 'list'],
            capture_output=True, text=True, timeout=3)
        for line in r.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 3 and parts[0] == '*':
                ssid = parts[1]
                signal = int(parts[2])  # nmcli 给出 0-100
                dbm = -90 + int(signal * 60 / 100)
                return ssid, dbm, signal
    except:
        pass

    try:
        # 方法2: iw dev (需安装 iw 包)
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
            return '', 0, 0
        r = subprocess.run(['iw', 'dev', iface, 'link'], capture_output=True, text=True, timeout=3)
        ssid = ''
        signal = 0
        for line in r.stdout.split('\n'):
            s = line.strip()
            if s.startswith('SSID:'):
                ssid = s.split(':', 1)[1].strip()
            elif 'signal:' in s:
                signal = int(s.split(':')[1].strip().split()[0])
        quality = max(0, min(100, round((signal + 90) * 100 / 60)))
        return ssid or iface, signal, quality
    except:
        pass

    try:
        # 方法3: /proc/net/wireless (内核接口)
        with open('/proc/net/wireless', 'r') as f:
            lines = f.readlines()
            if len(lines) >= 3:
                for line in lines[2:]:
                    parts = line.split()
                    if len(parts) >= 4 and ':' in parts[0]:
                        iface = parts[0].rstrip(':')
                        link_q = int(parts[2].rstrip('.'))  # 0~70 typical
                        quality = min(100, link_q * 100 // 70)
                        dbm = -90 + int(quality * 60 / 100)
                        return iface, dbm, quality
    except:
        pass

    return '', 0, 0


# ==================== 主程序 ====================
def main():
    print("ST7789 初始化中...")
    disp = ST7789()
    disp.init()
    print("初始化完成，启动系统监控")

    try:
        while True:
            cpu = get_cpu_usage()
            cpu_temp = get_cpu_temp()
            mem_used, mem_total, mem_pct = get_memory()
            wifi_ssid, wifi_dbm, wifi_q = get_wifi_info()
            print(f"CPU: {cpu:.1f}%  MEM: {mem_pct:.1f}%  WiFi: {wifi_ssid} {wifi_dbm}dBm")
            draw_dashboard(disp, cpu, cpu_temp, mem_used, mem_total, mem_pct,
                           wifi_ssid, wifi_dbm, wifi_q)
            time.sleep(1)
    except KeyboardInterrupt:
        disp.close()
        print("程序退出")


if __name__ == "__main__":
    main()
