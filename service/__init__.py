"""设备服务层：键盘输入、系统信息采集、网络、systemd 与后台采样。

按功能拆分为多个模块，并在此统一重导出，便于 main 引用：
  from service import KeyReader, BackgroundSampler, get_cpu_usage, ...
"""
from .keyboard import KeyReader
from .sampler import BackgroundSampler
from .sysinfo import get_cpu_usage, get_cpu_temp, get_fan_rpm, get_memory, get_disk_usage, get_uptime
from .network import (
    get_wifi_info, get_ip_address, detect_net_iface, read_net_bytes,
)
from .systemd import (
    get_services, get_service_status, get_service_logs, control_service,
    toggle_autostart,
)
from .music import (
    MusicPlayer, get_hot_playlist, search_songs, get_song_url,
)
from .camera import CameraStream

__all__ = [
    'KeyReader', 'BackgroundSampler',
    'get_cpu_usage', 'get_cpu_temp', 'get_fan_rpm', 'get_memory',
    'get_wifi_info', 'get_ip_address', 'detect_net_iface', 'read_net_bytes',
    'get_services', 'get_service_status', 'get_service_logs', 'control_service',
    'toggle_autostart',
    'get_disk_usage', 'get_uptime',
    'MusicPlayer', 'get_hot_playlist', 'search_songs', 'get_song_url',
    'CameraStream',
]
