"""摄像头帧采集：V4L2 read 接口，直接读 /dev/video0。

零外部依赖（仅标准库），无需 ffmpeg / OpenCV / v4l2 包。
"""
import os
import struct
import fcntl
import threading


# ── V4L2 ioctl 常量（通过 _IOWR 宏计算，aarch64 已验证）────────────
V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_PIX_FMT_YUYV = 0x56595559  # 'YUYV'

def _IOWR(type_, nr, size):
    return (3 << 30) | (ord(type_) << 8) | nr | (size << 16)

# struct v4l2_format 在 aarch64 上 = 200 字节
# struct v4l2_pix_format 占 48 字节，嵌入 type(4)+pad(4) 之后
VIDIOC_S_FMT = _IOWR('V', 5, 200)

def _vidioc_s_fmt(fd, w, h, pixfmt):
    """通过 S_FMT 设置摄像头采集格式。"""
    # v4l2_format {
    #   __u32 type;                    // 0-3
    #   struct v4l2_pix_format {       // 8-55 (offset 8, 4 字节 pad)
    #     __u32 width;                 // 8-11
    #     __u32 height;                // 12-15
    #     __u32 pixelformat;           // 16-19
    #     __u32 field;                 // 20-23
    #     __u32 bytesperline;          // 24-27
    #     __u32 sizeimage;             // 28-31
    #     __u32 colorspace;            // 32-35
    #     __u32 priv;                  // 36-39
    #     __u32 flags;                 // 40-43
    #     __u32 ycbcr_enc;             // 44-47
    #     __u32 quantization;          // 48-51
    #     __u32 xfer_func;             // 52-55
    #   }
    #   __u8 raw_data[144];           // 56-199 (填充)
    # }
    fmt = struct.pack('I4x', V4L2_BUF_TYPE_VIDEO_CAPTURE)
    fmt += struct.pack('IIIIIIIIIII', w, h, pixfmt,
                       0, 0, w * h * 2, 0, 0, 0, 0, 0, 0)
    fmt += b'\x00' * (200 - len(fmt))
    fcntl.ioctl(fd, VIDIOC_S_FMT, fmt)


# ── YUYV → RGB565 ─────────────────────────────────────────────────
def _yuyv_to_rgb565(y0, u, y1, v):
    y0 -= 16; y1 -= 16; u -= 128; v -= 128
    r0 = max(0, min(31, (298 * y0 + 409 * v + 128) >> 8))
    g0 = max(0, min(63, (298 * y0 - 100 * u - 208 * v + 128) >> 8))
    b0 = max(0, min(31, (298 * y0 + 516 * u + 128) >> 8))
    r1 = max(0, min(31, (298 * y1 + 409 * v + 128) >> 8))
    g1 = max(0, min(63, (298 * y1 - 100 * u - 208 * v + 128) >> 8))
    b1 = max(0, min(31, (298 * y1 + 516 * u + 128) >> 8))
    return (r0 << 11) | (g0 << 5) | b0, (r1 << 11) | (g1 << 5) | b1


def _yuyv_to_rgb565_frame(data, w, h):
    out = bytearray(w * h * 2)
    n = w * h // 2
    for i in range(n):
        off = i * 4
        y0, u, y1, v = data[off:off+4]
        p0, p1 = _yuyv_to_rgb565(y0, u, y1, v)
        out[i*4:i*4+4] = struct.pack('>HH', p0, p1)
    return bytes(out)


# ── 摄像头帧流（后台线程） ─────────────────────────────────────────
class CameraStream:
    """通过 V4L2 read 接口后台线程持续采集摄像头帧。

    >>> cam = CameraStream()
    >>> cam.start()
    >>> frame = cam.get()   # RGB565 bytes（大端序）或 None
    >>> cam.stop()
    """

    def __init__(self, device='/dev/video0', width=320, height=240):
        self.device = device
        self.w = width
        self.h = height
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._fd = None

    def start(self):
        self._fd = os.open(self.device, os.O_RDWR)
        try:
            _vidioc_s_fmt(self._fd, self.w, self.h, V4L2_PIX_FMT_YUYV)
        except Exception:
            os.close(self._fd)
            self._fd = None
            raise
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def get(self):
        with self._lock:
            return self._frame

    def stop(self):
        self._stop.set()
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _run(self):
        frame_size = self.w * self.h * 2
        while not self._stop.is_set():
            try:
                raw = os.read(self._fd, frame_size)
                if len(raw) != frame_size:
                    continue
                rgb = _yuyv_to_rgb565_frame(raw, self.w, self.h)
                with self._lock:
                    self._frame = rgb
            except OSError:
                break
