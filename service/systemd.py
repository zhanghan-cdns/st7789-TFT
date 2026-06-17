"""systemd 服务列表采集。"""
import subprocess


def get_services():
    """返回 [(name, active, sub, enabled), ...]

    合并 list-units（运行态）与 list-unit-files（自启配置）两份信息，
    排序：已启动（active）在前，未启动在后；组内按名称首字母排列。
    """
    svcs = {}
    try:
        r = subprocess.run(
            ['systemctl', 'list-units', '--type=service', '--all',
             '--no-legend', '--no-pager'],
            capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().split('\n'):
            fields = line.split()
            if not fields:
                continue
            # 行首可能有状态圆点（●/*，systemd 对 failed/activating 会标色），
            # 以 .service 结尾的单元名为锚点定位，避免圆点导致整行被跳过。
            idx = next((j for j, t in enumerate(fields)
                        if t.endswith('.service')), None)
            if idx is None or len(fields) < idx + 4:
                continue
            svcs[fields[idx]] = {'active': fields[idx + 2],
                                 'sub': fields[idx + 3], 'enabled': ''}
    except:
        pass

    try:
        r = subprocess.run(
            ['systemctl', 'list-unit-files', '--type=service',
             '--no-legend', '--no-pager'],
            capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().split('\n'):
            parts = line.split()  # UNIT-FILE  STATE  [VENDOR-PRESET]
            if len(parts) < 2 or not parts[0].endswith('.service'):
                continue
            name, state = parts[0], parts[1]
            if name in svcs:
                svcs[name]['enabled'] = state
            else:
                # 已安装但从未启动/加载的自定义服务也补进来，确保可见
                svcs[name] = {'active': 'inactive', 'sub': 'dead', 'enabled': state}
    except:
        pass

    result = [(n, v['active'], v['sub'], v['enabled']) for n, v in svcs.items()]
    # 排序：已启动（active）在前，未启动在后；组内按名称首字母（不区分大小写）排
    result.sort(key=lambda x: (0 if x[1] == 'active' else 1, x[0].lower()))
    return result


def _fmt_bytes(s):
    """把字节数格式化为 K/M/G；未知（空或 UINT64 哨兵值）返回空串。"""
    try:
        n = int(s)
    except (TypeError, ValueError):
        return ''
    if n <= 0 or n > (1 << 60):  # MemoryCurrent 未知时常为 UINT64 最大值
        return ''
    f = float(n)
    for unit in ('B', 'K', 'M', 'G'):
        if f < 1024:
            return f"{f:.0f}{unit}" if unit == 'B' else f"{f:.1f}{unit}"
        f /= 1024
    return f"{f:.1f}T"


def get_service_logs(name, lines=8):
    """返回服务最近 lines 行日志（仅消息正文）。"""
    try:
        r = subprocess.run(
            ['journalctl', '-u', name, '-n', str(lines),
             '--no-pager', '-o', 'cat'],
            capture_output=True, text=True, timeout=10)
        out = [ln for ln in r.stdout.split('\n') if ln.strip()]
        return out[-lines:]
    except Exception:
        return []


def get_service_status(name, log_lines=8):
    """返回单个服务的详情与最近日志，供详情页显示。

    用 `systemctl show` 取 key=value 属性（稳定易解析），journalctl 取日志。
    """
    info = {'name': name, 'description': '', 'load': '', 'active': '',
            'sub': '', 'enabled': '', 'pid': '', 'memory': '', 'since': '',
            'logs': []}
    props = ['Description', 'LoadState', 'ActiveState', 'SubState',
             'UnitFileState', 'MainPID', 'MemoryCurrent', 'ActiveEnterTimestamp']
    try:
        r = subprocess.run(
            ['systemctl', 'show', name, '--no-pager',
             '--property=' + ','.join(props)],
            capture_output=True, text=True, timeout=10)
        kv = {}
        for line in r.stdout.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                kv[k] = v
        info['description'] = kv.get('Description', '')
        info['load'] = kv.get('LoadState', '')
        info['active'] = kv.get('ActiveState', '')
        info['sub'] = kv.get('SubState', '')
        info['enabled'] = kv.get('UnitFileState', '')
        pid = kv.get('MainPID', '0')
        info['pid'] = pid if pid not in ('', '0') else ''
        info['memory'] = _fmt_bytes(kv.get('MemoryCurrent', ''))
        info['since'] = kv.get('ActiveEnterTimestamp', '')
    except Exception:
        pass
    info['logs'] = get_service_logs(name, log_lines)
    return info


def control_service(name, action):
    """对服务执行 start/stop/restart，返回 (成功?, 提示文本)。需 root 权限。"""
    if action not in ('start', 'stop', 'restart'):
        return False, '未知操作'
    try:
        r = subprocess.run(['systemctl', action, name],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return True, {'start': '已启动', 'stop': '已停止',
                          'restart': '已重启'}[action]
        msg = (r.stderr or r.stdout).strip().split('\n')[0][:40]
        return False, msg or '操作失败'
    except subprocess.TimeoutExpired:
        return False, '操作超时'
    except Exception as e:
        return False, str(e)[:40]
