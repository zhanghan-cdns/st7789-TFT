"""九宫格菜单页（首页）

3x3 网格展示各功能入口，光标高亮当前选中项。预留项以暗色显示、不可进入。
数据（菜单项与光标）由 main 维护并传入，保持 UI 无状态约定。
"""
from color import (
    BLACK, WHITE, CYAN, GREEN, MAGENTA, YELLOW, ORANGE, DGRAY, LGRAY,
    CARD, CPU_CLR,
)

# 菜单项：page 为对应子页标识，None 表示预留位（不可进入）
MENU_ITEMS = [
    {'label': '系统监控', 'color': CPU_CLR, 'page': 'dashboard'},
    {'label': '时间显示', 'color': CYAN, 'page': 'clock'},
    {'label': '系统服务', 'color': GREEN, 'page': 'services'},
    {'label': '音乐播放', 'color': MAGENTA, 'page': 'music'},
    {'label': '预留', 'color': DGRAY, 'page': None},
    {'label': '预留', 'color': DGRAY, 'page': None},
    {'label': '预留', 'color': DGRAY, 'page': None},
    {'label': '预留', 'color': DGRAY, 'page': None},
    {'label': '预留', 'color': DGRAY, 'page': None},
]

COLS = 3
MARGIN = 6
GAP = 8
TOP = 40
HL = 0x3186  # 选中高亮底色


def move_cursor(cursor, action, total=9):
    """根据方向键移动九宫格光标，返回新的光标索引（带边界钳制）"""
    row, col = cursor // COLS, cursor % COLS
    rows = (total + COLS - 1) // COLS
    if action == 'up' and row > 0:
        cursor -= COLS
    elif action == 'down' and row < rows - 1 and cursor + COLS < total:
        cursor += COLS
    elif action == 'left' and col > 0:
        cursor -= 1
    elif action == 'right' and col < COLS - 1 and cursor + 1 < total:
        cursor += 1
    return cursor


def draw_menu(disp, items, cursor):
    """绘制九宫格菜单

    参数：
      items  — 菜单项列表（见 MENU_ITEMS），每项含 label/color/page
      cursor — 当前选中项索引（0~8）
    """
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    # 顶栏标题
    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, "菜单", CYAN, size=16)

    cell_w = (W - 2 * MARGIN - (COLS - 1) * GAP) // COLS
    cell_h = (H - 16 - TOP - 2 * GAP) // 3

    for i, item in enumerate(items):
        row, col = i // COLS, i % COLS
        x = MARGIN + col * (cell_w + GAP)
        y = TOP + row * (cell_h + GAP)
        reserved = item['page'] is None

        bg = HL if i == cursor else CARD
        disp.fill_round_rect(x, y, cell_w, cell_h, 8, bg)

        # 图标圆点（预留位用暗灰）
        dot = item['color'] if not reserved else DGRAY
        disp.fill_circle(x + cell_w // 2, y + 18, 10, dot)

        # 标签居中
        label = item['label']
        lw, _ = disp.text_size_pil(label, 14)
        text_clr = WHITE if not reserved else DGRAY
        if i == cursor and not reserved:
            text_clr = item['color']
        disp.draw_text_pil(x + (cell_w - lw) // 2, y + cell_h - 22, label,
                           text_clr, size=14)

    # 底部操作提示
    hint = "↑↓←→选择  Enter进入  q退出"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil((W - hw) // 2, H - 13, hint, DGRAY, size=10)

    disp.flush()
