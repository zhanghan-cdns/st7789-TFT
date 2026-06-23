"""九宫格菜单页（首页）

3x3 网格展示各功能入口，光标高亮当前选中项。预留项以暗色显示、不可进入。
数据（菜单项与光标）由 main 维护并传入，保持 UI 无状态约定。
"""
from color import (
    WHITE, CYAN, GREEN, MAGENTA, YELLOW, ORANGE, DGRAY, LGRAY,
    CARD, CPU_CLR, BLUE,
)
from .icons import get_icon
from .dashboard import draw_page_frame

ICON_SIZE = 30  # 菜单图标边长（像素）

# 菜单项：page 为对应子页标识，None 表示预留位（不可进入）
MENU_ITEMS = [
    {'label': '系统监控', 'color': CPU_CLR, 'page': 'dashboard'},
    {'label': '时间显示', 'color': CYAN, 'page': 'clock'},
    {'label': '系统服务', 'color': GREEN, 'page': 'services'},
    {'label': '音乐播放', 'color': MAGENTA, 'page': 'music'},
    {'label': '摄像头', 'color': BLUE, 'page': 'camera'},
    {'label': '关机', 'color': ORANGE, 'page': 'shutdown'},
    {'label': '更新', 'color': YELLOW, 'page': 'update'},
    {'label': '设备信息', 'color': CYAN, 'page': 'device'},
    {'label': '预留', 'color': DGRAY, 'page': None},
]

COLS = 3
MARGIN = 6
GAP = 8
TOP = 40
HL = GREEN  # 选中高亮底色（绿色）


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
    draw_page_frame(disp, "MENU")

    cell_w = (W - 2 * MARGIN - (COLS - 1) * GAP) // COLS
    cell_h = (H - 16 - TOP - 2 * GAP) // 3

    for i, item in enumerate(items):
        row, col = i // COLS, i % COLS
        x = MARGIN + col * (cell_w + GAP)
        y = TOP + row * (cell_h + GAP)
        reserved = item['page'] is None

        bg = HL if i == cursor else CARD
        disp.fill_round_rect(x, y, cell_w, cell_h, 8, bg)

        # 图标（预留位用暗灰）：SVG 蒙版着色绘制，渲染失败回退为圆点
        # 已移除文字标签，图标在格子内垂直居中；选中项图标用白色
        if reserved:
            icon_clr = DGRAY
        elif i == cursor:
            icon_clr = WHITE
        else:
            icon_clr = item['color']
        icon = None if reserved else get_icon(item['page'], ICON_SIZE)
        if icon is not None:
            disp.blit_mask(x + (cell_w - ICON_SIZE) // 2,
                           y + (cell_h - ICON_SIZE) // 2, icon, icon_clr)
        else:
            disp.fill_circle(x + cell_w // 2, y + cell_h // 2, 10, icon_clr)

    # 底部操作提示
    hint = "Move: arrows   Enter: open   q: quit"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil((W - hw) // 2, H - 13, hint, DGRAY, size=10)

    disp.flush()
