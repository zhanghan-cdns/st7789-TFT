"""摄像头帧采集：常驻 ffmpeg 进程持续输出 raw RGB565，后台线程读帧。"""
import subprocess
import threading


class CameraStream:
    """保持 ffmpeg 子进程持续输出，后台线程循环读取最新一帧。

    用法：
      cam = CameraStream('/dev/video0')
      cam.start()
      frame = cam.get()       # 返回 bytes 或 None
      cam.stop()
    """

    def __init__(self, device='/dev/video0', width=320, height=240):
        self.device = device
        self.w = width
        self.h = height
        self.frame_size = width * height * 2
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._proc = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        cmd = [
            'ffmpeg', '-f', 'v4l2',
            '-video_size', f'{self.w}x{self.h}',
            '-i', self.device,
            '-f', 'rawvideo',
            '-pix_fmt', 'rgb565',
            '-loglevel', 'error',
            '-',
        ]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=self.frame_size * 2)
        except Exception:
            return

        while not self._stop.is_set():
            try:
                buf = self._proc.stdout.read(self.frame_size)
                if not buf or len(buf) < self.frame_size:
                    break
                buf = bytearray(buf)
                buf[0::2], buf[1::2] = buf[1::2], buf[0::2]
                with self._lock:
                    self._frame = bytes(buf)
            except Exception:
                break

    def get(self):
        with self._lock:
            return self._frame

    def stop(self):
        self._stop.set()
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
            self._proc = None
