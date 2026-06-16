"""系统服务列表（第三屏）

显示 systemd 服务的运行状态与自启配置。
数据由 main 采集后传入，支持上下翻页滚动浏览。
"""
from color import BLACK, WHITE, GREEN, RED, CYAN, ORANGE, YELLOW, DGRAY, LGRAY, CARD

ROWS_PER_PAGE = 7
ROW_HEIGHT = 24


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

    start = scroll
    end = min(start + ROWS_PER_PAGE, total)
    y = 40
    for i in range(start, end):
        name, active, sub, enabled = services[i]

        display_name = name
        if display_name.endswith('.service'):
            display_name = display_name[:-8]
        if len(display_name) > 24:
            display_name = display_name[:22] + '..'

        if i == cursor:
            disp.fill_rect(6, y, W - 12, ROW_HEIGHT, 0x3186)

        dot_color = _active_color(sub)
        disp.fill_circle(16, y + ROW_HEIGHT // 2, 5, dot_color)

        name_clr = WHITE if i != cursor else CYAN
        disp.draw_text_pil(28, y + 2, display_name, name_clr, size=12)

        en_label = _enabled_label(enabled)
        en_color = _enabled_color(enabled)
        en_w = disp.text_width_pil(en_label, 12)
        disp.draw_text_pil(W - 14 - en_w, y + 2, en_label, en_color, size=12)

        y += ROW_HEIGHT

    disp.draw_text_pil(6, H - 12, "↑↓选择  ←→翻页", DGRAY, size=10)
    disp.flush()
