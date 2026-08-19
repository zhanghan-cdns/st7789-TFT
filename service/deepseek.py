"""DeepSeek 余额查询：GET /user/balance，仅用标准库 urllib。

API Key 从环境变量 DEEPSEEK_API_KEY 读取（不落盘、不进代码仓库）。
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


def get_balance():
    """查询 DeepSeek 账号余额。

    返回 dict：
      成功: {'ok': True, 'is_available': bool, 'currency': str,
            'total': str, 'granted': str, 'topped_up': str, 'ts': float}
      失败: {'ok': False, 'error': str}  （未配置 Key / 网络 / HTTP 错误）
    """
    api_key = os.environ.get(KEY_ENV, '').strip()
    if not api_key:
        return {'ok': False, 'error': f'未设置 {KEY_ENV} 环境变量'}
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
