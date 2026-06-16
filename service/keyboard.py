"""物理键盘按键读取（Linux）

优先 evdev（/dev/input/event*，由内核输入层提供事件，不依赖终端焦点），
读不到设备时回退到终端 stdin 方向键转义序列。供主循环非阻塞轮询，
返回 'up'/'down'/'left'/'right'/'quit' 或 None。
"""
import os
import sys
import time
import glob
import select
import struct
import termios
import tty

# Linux input_event 结构：long sec, long usec, u16 type, u16 code, s32 value
_EV_FMT = 'llHHi'
_EV_SIZE = struct.calcsize(_EV_FMT)
_EV_KEY = 0x01           # 按键事件类型
# 键码（include/uapi/linux/input-event-codes.h）
_KEY_ESC = 1
_KEY_ENTER = 28
_KEY_Q = 16
_KEY_UP = 103
_KEY_DOWN = 108
_KEY_LEFT = 105
_KEY_RIGHT = 106
_KEY_KPENTER = 96  # 小键盘回车
# 键码 -> 动作映射
_KEYMAP = {
    _KEY_UP: 'up',
    _KEY_DOWN: 'down',
    _KEY_LEFT: 'left',
    _KEY_RIGHT: 'right',
    _KEY_ENTER: 'enter',
    _KEY_KPENTER: 'enter',
    _KEY_Q: 'quit',
    _KEY_ESC: 'back',
}


class KeyReader:
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
        if data in (b'\r', b'\n'):
            return 'enter'
        if data == b'\x1b':  # 单独的 ESC（非方向键转义序列）
            return 'back'
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
