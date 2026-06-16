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
