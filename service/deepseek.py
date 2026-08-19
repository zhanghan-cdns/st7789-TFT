"""DeepSeek 余额查询：GET /user/balance，仅用标准库 urllib。

API Key 从 config.json 的 deepseek.api_key 读取（环境变量 DEEPSEEK_API_KEY 兜底）。
网络调用可能阻塞，建议配合 BackgroundSampler 在后台线程定时刷新。
"""
import json
import os
import time
import urllib.error
import urllib.request

BALANCE_URL = 'https://api.deepseek.com/user/balance'
KEY_ENV = 'DEEPSEEK_API_KEY'

_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
}

# 配置文件路径（项目根目录 config.json）
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')


def _get_api_key():
    """读取 API Key：优先环境变量，其次 config.json 的 deepseek.api_key"""
    key = os.environ.get(KEY_ENV, '').strip()
    if key:
        return key
    try:
        with open(_CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
        return (cfg.get('deepseek') or {}).get('api_key', '').strip()
    except Exception:
        return ''


def get_balance():
    """查询 DeepSeek 账号余额。

    返回 dict：
      成功: {'ok': True, 'is_available': bool, 'currency': str,
            'total': str, 'granted': str, 'topped_up': str, 'ts': float}
      失败: {'ok': False, 'error': str}  （未配置 Key / 网络 / HTTP 错误）
    """
    api_key = _get_api_key()
    if not api_key:
        return {'ok': False, 'error': '未配置 API Key（config.json 的 deepseek.api_key）'}
    headers = dict(_HEADERS)
    headers['Authorization'] = f'Bearer {api_key}'
    try:
        req = urllib.request.Request(BALANCE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8', 'ignore'))
    except urllib.error.HTTPError as e:
        hint = '（API Key 无效）' if e.code == 401 else ''
        return {'ok': False, 'error': f'HTTP {e.code}{hint}'}
    except Exception as e:
        return {'ok': False, 'error': f'网络错误: {e}'}

    infos = data.get('balance_infos') or []
    if not infos:
        return {'ok': False, 'error': '响应无余额数据'}
    info = infos[0]
    return {
        'ok': True,
        'is_available': bool(data.get('is_available')),
        'currency': info.get('currency', 'CNY'),
        'total': info.get('total_balance', '0.00'),
        'granted': info.get('granted_balance', '0.00'),
        'topped_up': info.get('topped_up_balance', '0.00'),
        'ts': time.time(),
    }
