"""音乐播放页

展示歌曲列表与当前播放状态。数据（歌单、光标、播放状态）由 main 维护并传入，
保持 UI 无状态约定。列表支持上下滚动浏览。
"""
from color import (
    BLACK, WHITE, GREEN, CYAN, MAGENTA, ORANGE, DGRAY, LGRAY, CARD, TRACK,
)

ROWS_PER_PAGE = 6
ROW_HEIGHT = 24

_STATUS_TEXT = {'playing': '播放中', 'paused': '已暂停', 'stopped': '已停止'}
_STATUS_COLOR = {'playing': GREEN, 'paused': ORANGE, 'stopped': LGRAY}


def draw_music(disp, songs, cursor=0, scroll=0,
               playing_index=-1, status='stopped', loading=False):
    """绘制音乐播放页

    参数：
      songs         — 歌曲列表，每项含 name/artist
      cursor        — 当前选中行索引
      scroll        — 列表滚动起始索引
      playing_index — 正在播放的歌曲索引，-1 表示无
      status        — 'playing'/'paused'/'stopped'
      loading       — True 时显示加载中提示
    """
    W = disp.width
    H = disp.height
    total = len(songs)
    disp.fill_screen(BLACK)

    # 顶栏标题
    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, "音乐播放", CYAN, size=16)
    if not loading and total:
        info = f"{cursor + 1}/{total}"
        disp.draw_text_pil(W - 14 - disp.text_width_pil(info, 10), 15,
                           info, WHITE, size=10)

    # 列表为空：加载中 / 加载失败
    if loading or not total:
        msg = "歌单加载中..." if loading else "歌单加载失败，按 Esc 返回"
        mw, mh = disp.text_size_pil(msg, 16)
        disp.draw_text_pil((W - mw) // 2, (H - mh) // 2, msg, LGRAY, size=16)
        disp.flush()
        return

    start = scroll
    end = min(start + ROWS_PER_PAGE, total)
    y = 40
    for i in range(start, end):
        name = songs[i].get('name', '')
        artist = songs[i].get('artist', '')

        if i == cursor:
            disp.fill_rect(6, y, W - 12, ROW_HEIGHT, 0x3186)

        # 正在播放标记
        if i == playing_index:
            disp.fill_circle(16, y + ROW_HEIGHT // 2, 4, _STATUS_COLOR[status])

        title = name
        if len(title) > 16:
            title = title[:15] + '…'
        name_clr = MAGENTA if i == playing_index else (
            CYAN if i == cursor else WHITE)
        disp.draw_text_pil(28, y + 6, title, name_clr, size=13)

        if artist:
            aw = disp.text_width_pil(artist, 11)
            disp.draw_text_pil(W - 14 - aw, y + 7, artist, LGRAY, size=11)

        y += ROW_HEIGHT

    # 底部状态栏
    disp.fill_round_rect(6, H - 46, W - 12, 30, 6, CARD)
    st_text = _STATUS_TEXT.get(status, '')
    st_clr = _STATUS_COLOR.get(status, LGRAY)
    if 0 <= playing_index < total:
        now = songs[playing_index].get('name', '')
        line = f"♪ {now}"
        if len(line) > 18:
            line = line[:17] + '…'
    else:
        line = "未播放"
    disp.draw_text_pil(14, H - 39, line, WHITE, size=13)
    disp.draw_text_pil(W - 14 - disp.text_width_pil(st_text, 12), H - 38,
                       st_text, st_clr, size=12)

    disp.draw_text_pil(6, H - 12, "↑↓选择  Enter播放  Esc返回", DGRAY, size=10)
    disp.flush()


def _fmt_time(sec):
    """秒数格式化为 m:ss"""
    sec = int(max(0, sec))
    return f"{sec // 60}:{sec % 60:02d}"


def draw_now_playing(disp, song, status, elapsed, duration):
    """绘制“正在播放”详情页（含音频进度条）

    参数：
      song     — 当前曲目 {name, artist}
      status   — 'playing'/'paused'/'stopped'
      elapsed  — 已播放秒数
      duration — 总时长秒数（0 表示未知）
    """
    W = disp.width
    H = disp.height
    disp.fill_screen(BLACK)

    # 顶栏标题
    disp.fill_round_rect(6, 6, W - 12, 28, 6, CARD)
    disp.draw_text_pil(16, 11, "正在播放", CYAN, size=16)

    # 曲名（居中，过长截断）
    name = song.get('name', '') if song else ''
    if len(name) > 14:
        name = name[:13] + '…'
    nw, _ = disp.text_size_pil(name, 24)
    disp.draw_text_pil((W - nw) // 2, 66, name, WHITE, size=24)

    # 歌手（居中）
    artist = song.get('artist', '') if song else ''
    if artist:
        aw, _ = disp.text_size_pil(artist, 14)
        disp.draw_text_pil((W - aw) // 2, 104, artist, LGRAY, size=14)

    # 进度条
    bar_x, bar_y, bar_w, bar_h = 24, 150, W - 48, 10
    disp.fill_round_rect(bar_x, bar_y, bar_w, bar_h, bar_h // 2, TRACK)
    frac = (elapsed / duration) if duration > 0 else 0.0
    frac = max(0.0, min(1.0, frac))
    fw = int(bar_w * frac)
    if fw > 0:
        disp.fill_round_rect(bar_x, bar_y, max(fw, bar_h), bar_h,
                             bar_h // 2, MAGENTA)

    # 时间标签：已播放 / 总时长
    disp.draw_text_pil(bar_x, bar_y + 16, _fmt_time(elapsed), LGRAY, size=11)
    total_str = _fmt_time(duration) if duration > 0 else "--:--"
    disp.draw_text_pil(bar_x + bar_w - disp.text_width_pil(total_str, 11),
                       bar_y + 16, total_str, LGRAY, size=11)

    # 状态
    st_text = _STATUS_TEXT.get(status, '')
    st_clr = _STATUS_COLOR.get(status, LGRAY)
    sw, _ = disp.text_size_pil(st_text, 14)
    disp.draw_text_pil((W - sw) // 2, 192, st_text, st_clr, size=14)

    # 操作提示
    hint = "Enter 播放/暂停  ←→ 切歌  Esc 返回"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil((W - hw) // 2, H - 13, hint, DGRAY, size=10)

    disp.flush()
