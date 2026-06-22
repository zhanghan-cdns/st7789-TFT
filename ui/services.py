"""系统服务列表（第三屏）

显示 systemd 服务的运行状态与自启配置。
数据由 main 采集后传入，支持上下翻页滚动浏览。
"""
from color import BLACK, WHITE, GREEN, RED, CYAN, ORANGE, YELLOW, DGRAY, LGRAY, CARD

ROWS_PER_PAGE = 5
ROW_HEIGHT = 32

# 详情页操作按钮：(systemctl 动作, 显示文字)，运行时隐藏"启动"
def get_actions(active):
    """根据服务 active 状态返回可用操作按钮列表"""
    if active == 'active':
        return [('stop', '停止'), ('restart', '重启')]
    return [('start', '启动'), ('restart', '重启')]


def _active_color(sub):
    if sub == 'running':
        return GREEN
    if sub == 'exited':
        return CYAN
    if sub in ('failed', 'error'):
        return RED
    return LGRAY


def _enabled_color(state):
    if state == 'enabled':
        return GREEN
    if state == 'disabled':
        return RED
    return ORANGE


def _enabled_label(state):
    return {'enabled': '启用', 'disabled': '禁用',
            'static': '静态', 'indirect': '间接'}.get(state, '--')


def _active_label(sub):
    return {'running': '运行中', 'exited': '已退出', 'failed': '失败',
            'dead': '停止', 'inactive': '未激活'}.get(sub, sub)


def draw_services(disp, services, cursor=0, scroll=0):
    """绘制系统服务列表"""
    W = disp.width
    H = disp.height
    total = len(services)
    disp.fill_screen(BLACK)

    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, "系统服务", CYAN, size=16)
    max_page = max((total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE, 1)
    cur_page = scroll // ROWS_PER_PAGE + 1
    info = f"共 {total} 个 第 {cur_page}/{max_page} 页  光标 {cursor+1}/{total}"
    disp.draw_text_pil(W - 14 - disp.text_width_pil(info, 10), 15, info, WHITE, size=10)

    # 列头
    disp.draw_text_pil(28, 36, "服务名称", DGRAY, size=10)
    en_header = "自启"
    en_w = disp.text_width_pil(en_header, 10)
    disp.draw_text_pil(W - 14 - en_w, 36, en_header, DGRAY, size=10)

    start = scroll
    end = min(start + ROWS_PER_PAGE, total)
    y = 52
    for i in range(start, end):
        name, active, sub, enabled = services[i]

        display_name = name
        if display_name.endswith('.service'):
            display_name = display_name[:-8]
        if len(display_name) > 18:
            display_name = display_name[:16] + '..'

        if i == cursor:
            disp.fill_rect(6, y, W - 12, ROW_HEIGHT, 0x3186)

        dot_color = _active_color(sub)
        disp.fill_circle(16, y + ROW_HEIGHT // 2, 5, dot_color)

        name_clr = WHITE if i != cursor else CYAN
        disp.draw_text_pil(28, y + 4, display_name, name_clr, size=16)

        en_label = _enabled_label(enabled)
        en_color = _enabled_color(enabled)
        en_w = disp.text_width_pil(en_label, 16)
        disp.draw_text_pil(W - 14 - en_w, y + 4, en_label, en_color, size=16)

        y += ROW_HEIGHT

    disp.draw_text_pil(6, H - 12, "↑↓选择 ←→翻页 Enter详情", DGRAY, size=10)
    disp.flush()


def draw_service_detail(disp, detail, action_cursor=0, msg='',
                        focus='action', log_scroll=0):
    """绘制系统服务详情页：状态信息 + 操作按钮 + 最近日志

    参数：
      detail        — get_service_status 返回的字典，None 表示加载中
      action_cursor — 当前选中的操作按钮索引（见 ACTIONS）
      msg           — 操作结果/状态提示文本
      focus         — 焦点区域：'action' 按钮区 / 'log' 日志区
      log_scroll    — 日志滚动偏移行数
    """
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    name = (detail.get('name', '') if detail else '')
    short = name[:-8] if name.endswith('.service') else name
    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, short[:26], CYAN, size=16)

    if not detail:
        disp.draw_text_pil(16, 70, "加载中...", LGRAY, size=14)
        disp.flush()
        return

    # 状态信息
    y = 40
    active = detail.get('active', '')
    sub = detail.get('sub', '')
    act_clr = (GREEN if active == 'active'
               else RED if active == 'failed' else LGRAY)
    disp.draw_text_pil(12, y, "状态:", LGRAY, size=12)
    disp.draw_text_pil(56, y, f"{_active_label(sub)} ({active})", act_clr, size=12)
    y += 18

    en = detail.get('enabled', '')
    disp.draw_text_pil(12, y, "自启:", LGRAY, size=12)
    disp.draw_text_pil(56, y, _enabled_label(en), _enabled_color(en), size=12)
    extra = []
    if detail.get('pid'):
        extra.append(f"PID {detail['pid']}")
    if detail.get('memory'):
        extra.append(detail['memory'])
    if extra:
        disp.draw_text_pil(150, y, '  '.join(extra), WHITE, size=12)
    y += 18

    desc = detail.get('description', '')
    if desc:
        disp.draw_text_pil(12, y, desc[:40], DGRAY, size=11)
    y += 18

    # 操作按钮 + 自启开关（同一行）
    actions = get_actions(detail.get('active', ''))
    en = detail.get('enabled', '')
    n_act = len(actions)
    all_btns = actions + [('autostart', '自启:开' if en == 'enabled' else '自启:关')]
    bw, bh, gap = 70, 26, 6
    for i, (act, label) in enumerate(all_btns):
        x = 12 + i * (bw + gap)
        if act == 'autostart':
            sel = (action_cursor >= n_act)
            clr = GREEN if en == 'enabled' else RED
        else:
            sel = (i == action_cursor and action_cursor < n_act)
            clr = GREEN if sel else CARD
        bg = clr if sel else CARD
        txt_clr = BLACK if sel else (clr if act == 'autostart' else WHITE)
        disp.fill_round_rect(x, y, bw, bh, 6, bg)
        tw = disp.text_width_pil(label, 12)
        disp.draw_text_pil(x + (bw - tw) // 2, y + 6, label,
                           txt_clr, size=12)
    y += bh + 6

    if msg:
        disp.draw_text_pil(12, y, msg[:40], YELLOW, size=12)
    y += 18

    # 日志区
    logs = detail.get('logs', [])
    max_scroll = max(0, len(logs) - 1)
    if log_scroll > max_scroll:
        log_scroll = max_scroll
    disp.draw_text_pil(12, y, "日志:", LGRAY, size=11)
    y += 15
    for i in range(log_scroll, len(logs)):
        if y > H - 24:
            break
        disp.draw_text_pil(12, y, logs[i][:60], LGRAY, size=10)
        y += 13

    hint = "←→切换按钮  ↑↓翻日志  Enter执行  Esc返回"
    disp.draw_text_pil(6, H - 12, hint, DGRAY, size=10)
    disp.flush()
