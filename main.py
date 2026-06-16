"""ST7789 系统监控主程序

负责系统信息采集与主循环，调度 st7789_driver 驱动和 ui 渲染。
运行：python main.py
"""
import time
import os
import sys
import glob
import select
import struct
import termios
import tty
import threading
import subprocess

from st7789_driver import ST7789
from ui import draw_dashboard, draw_clock, draw_services, lunar_date_str, CPU_HISTORY_LEN

# 页面：0=系统监控，1=时钟，2=系统服务
NUM_PAGES = 3
WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


# ==================== 键盘输入 ====================
# Linux input_event 结构：long sec, long usec, u16 type, u16 code, s32 value
_EV_FMT = 'llHHi'
_EV_SIZE = struct.calcsize(_EV_FMT)
_EV_KEY = 0x01           # 按键事件类型
# 键码（include/uapi/linux/input-event-codes.h）
_KEY_ESC = 1
_KEY_Q = 16
_KEY_UP = 103
_KEY_DOWN = 108
_KEY_LEFT = 105
_KEY_RIGHT = 106
# 键码 -> 动作映射
_KEYMAP = {
    _KEY_UP: 'up',
    _KEY_DOWN: 'down',
    _KEY_LEFT: 'left',
    _KEY_RIGHT: 'right',
    _KEY_Q: 'quit',
    _KEY_ESC: 'quit',
}


class _KeyReader:
    """读取物理键盘按键（Linux）。

    优先直接读取输入事件设备 /dev/input/event*（evdev）：由内核输入层
    提供按键事件，不依赖终端焦点，适用于设备上直插键盘的场景（需要对
    输入设备的读权限，通常需 root 或加入 input 组）。若无法打开任何输入
    设备，则回退到读取终端 stdin 的方向键转义序列。
    """

    def __init__(self, debug=True):
        self.debug = debug
        self.mode = None
        self._evfds = []
        self._tty_fd = None
        self._tty_old = None

        # 1) 优先 evdev：打开所有可读的输入事件设备
        paths = sorted(glob.glob('/dev/input/event*'))
        print(f"[按键] 扫描到输入设备: {paths}")
        for path in paths:
            try:
                self._evfds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
            except OSError as e:
                if self.debug:
                    print(f"[按键] 打开 {path} 失败: {e}")
        if self._evfds:
            self.mode = 'evdev'
            print(f"[按键] 使用 evdev，监听 {len(self._evfds)} 个输入设备，"
                  f"_EV_SIZE={_EV_SIZE}")
            return

        # 2) 回退：终端 stdin 方向键
        if sys.stdin.isatty():
            self.mode = 'tty'
            self._tty_fd = sys.stdin.fileno()
            self._tty_old = termios.tcgetattr(self._tty_fd)
            tty.setcbreak(self._tty_fd)
            print("[按键] 无可用输入设备，回退到终端 stdin")
        else:
            print("[按键] 无可用输入设备，且非终端，按键功能禁用"
                  "（直插键盘请用 sudo 运行以读取 /dev/input/event*）")

    def poll(self, timeout):
        """等待至多 timeout 秒，返回 'left'/'right'/'quit' 或 None"""
        if self.mode == 'evdev':
            return self._poll_evdev(timeout)
        if self.mode == 'tty':
            return self._poll_tty(timeout)
        time.sleep(timeout)
        return None

    def _poll_evdev(self, timeout):
        r, _, _ = select.select(self._evfds, [], [], timeout)
        if not r:
            return None
        for fd in r:
            try:
                data = os.read(fd, _EV_SIZE * 64)
            except OSError:
                continue
            for off in range(0, len(data) - _EV_SIZE + 1, _EV_SIZE):
                _, _, etype, code, value = struct.unpack(
                    _EV_FMT, data[off:off + _EV_SIZE])
                if etype == _EV_KEY:
                    if self.debug:
                        print(f"[按键] EV_KEY code={code} value={value}")
                    if value == 1 and code in _KEYMAP:  # 仅按下沿
                        return _KEYMAP[code]
        return None

    def _poll_tty(self, timeout):
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if not r:
            return None
        data = os.read(self._tty_fd, 8)
        if self.debug:
            print(f"[按键] 读到原始字节: {data!r}")
        if data == b'\x1b[A':
            return 'up'
        if data == b'\x1b[B':
            return 'down'
        if data == b'\x1b[D':
            return 'left'
        if data == b'\x1b[C':
            return 'right'
        if data in (b'q', b'Q'):
            return 'quit'
        return None

    def restore(self):
        for fd in self._evfds:
            try:
                os.close(fd)
            except OSError:
                pass
        if self.mode == 'tty' and self._tty_old is not None:
            termios.tcsetattr(self._tty_fd, termios.TCSADRAIN, self._tty_old)


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


class _WifiSampler:
    """后台守护线程周期性采集 WiFi 信息。

    nmcli 扫描可能阻塞数秒，若放在主循环会卡住时钟刷新与按键轮询。
    这里在独立线程里采集，主循环只读最近一次缓存值，永不阻塞。
    """
    def __init__(self, interval=8.0):
        self.interval = interval
        self._value = ('', 0, 0)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            val = get_wifi_info()
            with self._lock:
                self._value = val
            self._stop.wait(self.interval)

    def get(self):
        with self._lock:
            return self._value

    def stop(self):
        self._stop.set()


# ==================== 系统服务采集 ====================
def get_services():
    """返回 [(name, active, sub, enabled), ...] 按状态+名称排序"""
    svcs = {}
    try:
        r = subprocess.run(
            ['systemctl', 'list-units', '--type=service', '--all',
             '--no-legend', '--no-pager'],
            capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().split('\n'):
            parts = line.split(maxsplit=4)
            if len(parts) >= 4 and parts[0].endswith('.service'):
                svcs[parts[0]] = {'active': parts[2], 'sub': parts[3], 'enabled': ''}
    except:
        pass

    try:
        r = subprocess.run(
            ['systemctl', 'list-unit-files', '--type=service',
             '--no-legend', '--no-pager'],
            capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().split('\n'):
            parts = line.split(maxsplit=1)
            if len(parts) >= 2 and parts[0] in svcs:
                svcs[parts[0]]['enabled'] = parts[1]
    except:
        pass

    order = {'running': 0, 'failed': 1, 'inactive': 2, 'dead': 3}
    result = [(n, v['active'], v['sub'], v['enabled']) for n, v in svcs.items()]
    result.sort(key=lambda x: (order.get(x[2], 9), x[0]))
    return result


class _ServicesSampler:
    """后台线程周期性采集系统服务列表"""
    def __init__(self, interval=30.0):
        self.interval = interval
        self._value = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        # 首次采集立即执行
        self._value = get_services()

    def _run(self):
        while not self._stop.is_set():
            val = get_services()
            with self._lock:
                self._value = val
            self._stop.wait(self.interval)

    def get(self):
        with self._lock:
            return self._value

    def stop(self):
        self._stop.set()


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
    # 强制行缓冲，避免输出被重定向/后台运行时 print 迟迟不刷新
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
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

    cpu_history = []

    net_iface = _detect_net_iface()
    prev_rx, prev_tx = _read_net_bytes(net_iface)
    net_ip = get_ip_address(net_iface)
    get_cpu_usage()  # 预热，建立 CPU 采样基准

    # 多页状态与按键读取
    page = 0
    services_scroll = 0
    keys = _KeyReader()
    print("← →切换页面（系统监控/时钟/系统服务），↑↓滚动服务列表，q 退出")

    # WiFi 采集放到后台线程，避免 nmcli 扫描阻塞主循环
    wifi_sampler = _WifiSampler()
    wifi_sampler.start()

    # 系统服务采集放到后台线程（每 30 秒刷新一次）
    services_sampler = _ServicesSampler()
    services_sampler.start()

    # 采样数据初值（首帧渲染用）
    cpu = 0.0
    cpu_temp = None
    fan_val = fan_unit = None
    mem_used = mem_total = mem_pct = 0
    wifi_ssid, wifi_dbm, wifi_q = '', 0, 0
    net_down = net_up = 0
    services_data = services_sampler.get()

    last_sample = 0.0
    need_render = True

    try:
        while True:
            # 每秒采样一次系统信息（与页面无关，保持历史与日志连续）
            if time.monotonic() - last_sample >= 1.0:
                last_sample = time.monotonic()
                cpu = get_cpu_usage()
                cpu_history.append(cpu)
                if len(cpu_history) > CPU_HISTORY_LEN:
                    cpu_history.pop(0)
                cpu_temp = get_cpu_temp()
                fan_val, fan_unit = get_fan_rpm()
                mem_used, mem_total, mem_pct = get_memory()
                wifi_ssid, wifi_dbm, wifi_q = wifi_sampler.get()

                # 刷新服务数据（后台线程每 30 秒自动更新）
                services_data = services_sampler.get()

                rx, tx = _read_net_bytes(net_iface)
                net_down = rx - prev_rx
                net_up = tx - prev_tx
                prev_rx, prev_tx = rx, tx

                temp_s = f"{cpu_temp:.0f}C" if cpu_temp is not None else "N/A"
                print(f"CPU: {cpu:.1f}%  MEM: {mem_pct:.1f}%  TEMP: {temp_s}  "
                      f"FAN: {fan_val}{fan_unit or ''}  WiFi: {wifi_ssid} "
                      f"NET ↓{net_down//1024}K ↑{net_up//1024}K")
                need_render = True  # 数据更新触发重绘（时钟页借此每秒刷新）

            if need_render:
                if page == 0:
                    draw_dashboard(disp, cpu, cpu_history, cpu_temp, fan_val, fan_unit,
                                   mem_used, mem_total, mem_pct,
                                   wifi_ssid, wifi_dbm, wifi_q,
                                   net_down, net_up, net_ip)
                elif page == 1:
                    lt = time.localtime()
                    draw_clock(disp,
                               time.strftime('%H:%M:%S', lt),
                               time.strftime('%Y-%m-%d', lt),
                               WEEKDAYS[lt.tm_wday],
                               lunar_date_str(lt.tm_year, lt.tm_mon, lt.tm_mday))
                else:
                    draw_services(disp, services_data, services_scroll)
                need_render = False

            # 细粒度轮询按键，使切换即时响应
            key = keys.poll(0.05)
            if key == 'left':
                page = (page - 1) % NUM_PAGES
                need_render = True
                print(f"[按键] 左 -> 切换到页面 {page}")
            elif key == 'right':
                page = (page + 1) % NUM_PAGES
                need_render = True
                print(f"[按键] 右 -> 切换到页面 {page}")
            elif key == 'up':
                if page == 2 and services_data:
                    svc_total = len(services_data)
                    services_scroll = max(0, services_scroll - 1)
                    print(f"[按键] 上 -> 服务滚动到 {services_scroll}")
                    need_render = True
            elif key == 'down':
                if page == 2 and services_data:
                    max_scroll = max(0, len(services_data) - 1)
                    services_scroll = min(max_scroll, services_scroll + 1)
                    print(f"[按键] 下 -> 服务滚动到 {services_scroll}")
                    need_render = True
            elif key == 'quit':
                break
    except KeyboardInterrupt:
        pass
    finally:
        wifi_sampler.stop()
        services_sampler.stop()
        keys.restore()
        disp.close()
        print("程序退出")


if __name__ == "__main__":
    main()
