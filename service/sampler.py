"""后台采样器：独立守护线程周期性采集，主循环只读缓存不阻塞。"""
import threading


class BackgroundSampler:
    """通用后台采样器。

    将可能阻塞的采集函数（如 nmcli 扫描、systemctl 查询）放到独立守护
    线程周期执行，主循环通过 get() 只读最近一次结果，避免阻塞刷新与按键。

    参数：
      func     —— 无参采集函数，返回值会被缓存
      interval —— 两次采集之间的间隔（秒）
      initial  —— 首次结果就绪前的初值
      eager    —— True 时在 start() 内先同步采集一次，使首帧即有数据
    """
    def __init__(self, func, interval, initial=None, eager=False):
        self._func = func
        self.interval = interval
        self._value = initial
        self._eager = eager
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if self._eager:
            self._value = self._func()  # 首次同步采集，使首帧即有数据
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            val = self._func()
            with self._lock:
                self._value = val
            self._stop.wait(self.interval)

    def get(self):
        with self._lock:
            return self._value

    def stop(self):
        self._stop.set()
