"""DeepSeek 本地代理：转发 + token 离线统计 + AI 红绿灯状态服务

用法（在 Windows 开发机上运行）：
    python deepseek_proxy.py            # 监听 0.0.0.0:8888
    python deepseek_proxy.py --port 9000

你的 DeepSeek 调用改一行即可被统计：
    base_url = "http://127.0.0.1:8888/v1"     # OpenAI SDK 风格
    api_key  任意（会原样转发给 DeepSeek）

功能：
  - 转发 /v1/* 到 https://api.deepseek.com（支持流式与非流式）
  - 从每次响应的 usage 字段精确统计 token，按小时存档到 ai_tokens.json
  - GET /state 返回红绿灯状态 + 今日 token + 24h 消耗曲线，供鲁班猫轮询
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_BASE = 'https://api.deepseek.com'
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ai_tokens.json')

# 请求结束后多久仍视为"调用中"（秒）
BUSY_WINDOW = 5.0

_lock = threading.Lock()
_last_active = 0.0     # 最近一次请求活跃时刻（monotonic）
_trae_busy = False     # Trae 探测器上报的调用状态（deepseek_detect.ps1）
_stats = {}            # {"YYYY-MM-DD": {"HH": {"p": n, "c": n}}}


def _load():
    global _stats
    try:
        with open(DATA_FILE, 'r') as f:
            _stats = json.load(f)
    except Exception:
        _stats = {}


def _save():
    tmp = DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_stats, f)
    os.replace(tmp, DATA_FILE)


def _record(prompt, completion):
    """累加一次请求的 token 消耗（按天/小时归档，仅保留近 14 天）"""
    global _stats
    with _lock:
        lt = time.localtime()
        day, hour = time.strftime('%Y-%m-%d', lt), time.strftime('%H', lt)
        day_stats = _stats.setdefault(day, {})
        h = day_stats.setdefault(hour, {'p': 0, 'c': 0})
        h['p'] += int(prompt or 0)
        h['c'] += int(completion or 0)
        for d in sorted(_stats.keys())[:-14]:
            del _stats[d]
        _save()


def _state():
    """组装 /state 响应：红绿灯 + 今日 token + 24h 曲线"""
    with _lock:
        busy = ((time.monotonic() - _last_active) < BUSY_WINDOW) or _trae_busy
        lt = time.localtime()
        day = time.strftime('%Y-%m-%d', lt)
        cur_hour = int(time.strftime('%H', lt))
        day_stats = _stats.get(day, {})
        hourly = []
        p = c = 0
        for h in range(24):
            hh = day_stats.get('%02d' % h, {})
            tp, tc = hh.get('p', 0), hh.get('c', 0)
            hourly.append({'h': h, 'prompt': tp, 'completion': tc, 'total': tp + tc})
            if h <= cur_hour:
                p += tp
                c += tc
        return {
            'busy': busy,
            'trae_busy': _trae_busy,
            'date': day,
            'today_tokens': {'prompt': p, 'completion': c, 'total': p + c},
            'hourly': hourly,
        }


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'DeepSeekProxy/1.0'

    # ---------- 辅助 ----------
    def _touch(self):
        with _lock:
            global _last_active
            _last_active = time.monotonic()

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_stream(self, body):
        if not body:
            return False
        try:
            return bool(json.loads(body).get('stream', False))
        except Exception:
            return False

    # ---------- 入口 ----------
    def do_GET(self):
        if self.path.split('?')[0] == '/state':
            self._send_json(200, _state())
        else:
            self._touch()
            self._proxy('GET')

    def do_POST(self):
        if self.path.split('?')[0] == '/report':
            return self._report()
        self._touch()
        self._proxy('POST')

    def _report(self):
        """接收 deepseek_detect.ps1 上报的 Trae 调用状态"""
        global _trae_busy
        ln = int(self.headers.get('Content-Length') or 0)
        try:
            obj = json.loads(self.rfile.read(ln).decode('utf-8', 'ignore')) if ln else {}
        except Exception:
            obj = {}
        with _lock:
            _trae_busy = bool(obj.get('trae_busy', False))
        self._send_json(200, {'ok': True})

    # ---------- 转发 ----------
    def _proxy(self, method):
        body = None
        if method == 'POST':
            ln = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(ln) if ln else None

        url = API_BASE + self.path
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ('host', 'connection',
                                        'accept-encoding', 'content-length')}
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            upstream = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            self._send_json(e.code, {'error': e.reason or 'upstream error'})
            return
        except Exception as e:
            self._send_json(502, {'error': f'proxy: {e}'})
            return

        try:
            if self._is_stream(body):
                self.send_response(upstream.getcode())
                self.send_header('Content-Type',
                                 upstream.headers.get('Content-Type',
                                                      'text/event-stream'))
                self.send_header('Connection', 'close')
                self.end_headers()
                self._relay_stream(upstream)
            else:
                data = upstream.read()
                self._record_from_json(data)
                self.send_response(upstream.getcode())
                self.send_header('Content-Type',
                                 upstream.headers.get('Content-Type',
                                                      'application/json'))
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        finally:
            upstream.close()

    def _relay_stream(self, upstream):
        """边转发 SSE 流边解析每帧中的 usage（stream_options.include_usage 时最后有）"""
        buf = b''
        while True:
            chunk = upstream.read(4096)
            if not chunk:
                break
            self._touch()
            self.wfile.write(chunk)
            self.wfile.flush()
            buf += chunk
            while b'\n\n' in buf:
                frame, buf = buf.split(b'\n\n', 1)
                text = frame.decode('utf-8', 'ignore').strip()
                if text.startswith('data:') and text != 'data: [DONE]':
                    try:
                        usage = json.loads(text[5:].strip()).get('usage')
                        if usage:
                            _record(usage.get('prompt_tokens'),
                                    usage.get('completion_tokens'))
                    except Exception:
                        pass

    def _record_from_json(self, data):
        try:
            usage = json.loads(data.decode('utf-8', 'ignore')).get('usage')
            if usage:
                _record(usage.get('prompt_tokens'),
                        usage.get('completion_tokens'))
        except Exception as e:
            sys.stderr.write('[proxy] record error: %r\n' % e)

    def log_message(self, fmt, *args):
        sys.stderr.write('[proxy] %s  %s\n' % (time.strftime('%H:%M:%S'), fmt % args))


def main():
    parser = argparse.ArgumentParser(description='DeepSeek 本地代理（转发 + token 统计 + 状态）')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址（默认 0.0.0.0）')
    parser.add_argument('--port', type=int, default=8888, help='监听端口（默认 8888）')
    args = parser.parse_args()

    _load()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'DeepSeek 代理已启动: http://{args.host}:{args.port}', flush=True)
    print(f'  调用 base_url: http://127.0.0.1:{args.port}/v1', flush=True)
    print(f'  状态接口:      http://<本机IP>:{args.port}/state', flush=True)
    print(f'  数据文件:      {DATA_FILE}', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已退出')


if __name__ == '__main__':
    main()
