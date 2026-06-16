"""网络相关采集：WiFi 信息、IP 地址、接口流量。

WiFi 用 nmcli（可能阻塞，建议配合 BackgroundSampler 在后台线程使用），
IP/流量读取较快，可在主循环直接调用。
"""
import os
import subprocess

_wifi_cache = None


def get_wifi_info():
    """返回 (ssid, signal_dbm, quality_pct)，失败时沿用上次缓存"""
    global _wifi_cache
    try:
        r = subprocess.run(
            ['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL', 'dev', 'wifi', 'list'],
            capture_output=True, text=True, timeout=5)
        for line in r.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 3 and parts[0] == '*':
                ssid = parts[1]
                signal = int(parts[2])
                dbm = -90 + int(signal * 60 / 100)
                _wifi_cache = (ssid, dbm, signal)
                return _wifi_cache
    except:
        pass
    if _wifi_cache is not None:
        return _wifi_cache
    return '', 0, 0


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


def detect_net_iface():
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


def read_net_bytes(iface):
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
