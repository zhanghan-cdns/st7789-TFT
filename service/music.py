"""网易云音乐：歌单/搜索接口 + 播放直链 + 本地播放器封装。

接口走网易云公开 HTTP 端点（仅用标准库 urllib，无第三方依赖）；
播放调用系统已安装的命令行播放器（mpv/ffplay/mpg123/cvlc，运行时探测）。
网络调用可能阻塞，建议配合 BackgroundSampler 在后台线程加载歌单。
"""
import json
import os
import shutil
import signal
import subprocess
import time
import urllib.parse
import urllib.request

# 默认歌单：网易云“云音乐热歌榜”
HOT_PLAYLIST_ID = 3778678

_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
    'Referer': 'https://music.163.com/',
}


def _http_get_json(url, timeout=8):
    """GET 请求并解析 JSON，失败返回 None"""
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8', 'ignore'))
    except Exception as e:
        print(f"[音乐] 请求失败: {e}")
        return None


def _parse_track(t):
    """从单曲 JSON 提取 {id, name, artist}，兼容新旧字段名"""
    artists = t.get('artists') or t.get('ar') or []
    artist = '/'.join(a.get('name', '') for a in artists if a.get('name'))
    # 总时长（毫秒）：旧接口为 duration，新接口为 dt
    duration = t.get('duration') or t.get('dt') or 0
    return {'id': t.get('id'), 'name': t.get('name', ''),
            'artist': artist, 'duration': duration}


def get_hot_playlist(limit=30):
    """获取热歌榜歌曲列表 [{id, name, artist}, ...]，失败返回 []"""
    url = f'https://music.163.com/api/playlist/detail?id={HOT_PLAYLIST_ID}'
    data = _http_get_json(url)
    if not data:
        return []
    result = data.get('result') or data.get('playlist') or {}
    tracks = result.get('tracks') or []
    songs = [_parse_track(t) for t in tracks[:limit]]
    print(f"[音乐] 歌单加载完成，共 {len(songs)} 首")
    return songs


def search_songs(keyword, limit=30):
    """按关键词搜索歌曲 [{id, name, artist}, ...]，失败返回 []"""
    kw = urllib.parse.quote(keyword)
    url = (f'https://music.163.com/api/search/get?s={kw}'
           f'&type=1&limit={limit}')
    data = _http_get_json(url)
    if not data:
        return []
    songs = (data.get('result') or {}).get('songs') or []
    return [_parse_track(t) for t in songs[:limit]]


def get_song_url(song_id):
    """返回歌曲播放直链（外链跳转，自动重定向到实际音频）"""
    return f'https://music.163.com/song/media/outer/url?id={song_id}.mp3'


# ==================== 本地播放器封装 ====================
# 各播放器命令前缀（按优先级；mpv/ffplay 对 https + 重定向支持最好）
_PLAYERS = [
    ('mpv', ['mpv', '--no-video', '--really-quiet']),
    ('ffplay', ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet']),
    ('mpg123', ['mpg123', '-q']),
    ('cvlc', ['cvlc', '--intf', 'dummy', '--play-and-exit']),
]


class MusicPlayer:
    """调用系统命令行播放器播放网络音频，支持播放/暂停/停止。

    暂停通过向播放进程发送 SIGSTOP/SIGCONT 实现（Linux）。
    """

    def __init__(self):
        self._proc = None
        self._paused = False
        self._duration = 0.0      # 当前曲目总时长（秒）
        self._start = 0.0         # 播放起始 monotonic 时间
        self._paused_accum = 0.0  # 累计暂停时长（秒）
        self._pause_start = None  # 本次暂停起点
        self._cmd = None
        for name, cmd in _PLAYERS:
            if shutil.which(cmd[0]):
                self._cmd = cmd
                print(f"[音乐] 使用播放器: {name}")
                break
        if self._cmd is None:
            print("[音乐] 未找到可用播放器（需安装 mpv/ffplay/mpg123/vlc 之一）")

    def available(self):
        return self._cmd is not None

    def play(self, url, duration=0):
        """播放指定直链，先停止当前播放

        duration —— 曲目总时长（秒），用于进度条；未知可传 0。
        """
        self.stop()
        if not self._cmd:
            return False
        try:
            self._proc = subprocess.Popen(
                self._cmd + [url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._paused = False
            self._duration = max(0.0, duration)
            self._start = time.monotonic()
            self._paused_accum = 0.0
            self._pause_start = None
            return True
        except Exception as e:
            print(f"[音乐] 播放失败: {e}")
            self._proc = None
            return False

    def toggle_pause(self):
        """暂停/恢复当前播放，返回新的暂停状态"""
        if self._proc is None or self._proc.poll() is not None:
            return False
        try:
            sig = signal.SIGCONT if self._paused else signal.SIGSTOP
            os.kill(self._proc.pid, sig)
            if self._paused:  # 恢复：累计本次暂停时长
                if self._pause_start is not None:
                    self._paused_accum += time.monotonic() - self._pause_start
                self._pause_start = None
            else:             # 暂停：记录起点
                self._pause_start = time.monotonic()
            self._paused = not self._paused
        except Exception as e:
            print(f"[音乐] 暂停切换失败: {e}")
        return self._paused

    def stop(self):
        """停止当前播放并回收进程"""
        if self._proc is not None:
            try:
                if self._paused:
                    os.kill(self._proc.pid, signal.SIGCONT)
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        self._paused = False
        self._pause_start = None

    def status(self):
        """返回 'playing' / 'paused' / 'stopped'（自动检测播放结束）"""
        if self._proc is None:
            return 'stopped'
        if self._proc.poll() is not None:
            self._proc = None
            self._paused = False
            self._pause_start = None
            return 'stopped'
        return 'paused' if self._paused else 'playing'

    def duration(self):
        """当前曲目总时长（秒），未知为 0"""
        return self._duration

    def elapsed(self):
        """已播放时长（秒，估算，扣除暂停时间）"""
        if self._proc is None or self._proc.poll() is not None:
            return 0.0
        sec = time.monotonic() - self._start - self._paused_accum
        if self._paused and self._pause_start is not None:
            sec -= time.monotonic() - self._pause_start
        if self._duration > 0:
            sec = min(sec, self._duration)
        return max(0.0, sec)
