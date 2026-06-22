"""ST7789 系统监控主程序

负责系统信息采集与主循环，调度 st7789_driver 驱动和 ui 渲染。
运行：python main.py
"""
import time
import sys
import glob
import os
import threading

from st7789_driver import ST7789
from ui import (
    draw_dashboard, draw_clock, draw_services, draw_service_detail,
    draw_menu, draw_music, draw_now_playing, draw_camera,
    move_cursor, MENU_ITEMS, lunar_date_str, lunar_yi_yi_str,
    get_actions, CPU_HISTORY_LEN,
)
from ui.services import ROWS_PER_PAGE as SVC_ROWS
from ui.music import ROWS_PER_PAGE as MUSIC_ROWS
from service import (
    KeyReader, BackgroundSampler,
    get_cpu_usage, get_cpu_temp, get_fan_rpm, get_memory,
    get_wifi_info, get_ip_address, get_services,
    get_service_status, control_service, toggle_autostart,
    detect_net_iface, read_net_bytes,
    MusicPlayer, get_hot_playlist, get_song_url,
    CameraStream,
)

WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


# ==================== 主程序 ====================
def main():
    # 强制行缓冲，避免输出被重定向/后台运行时 print 迟迟不刷新
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print("ST7789 初始化中...")
    disp = ST7789()
    disp.init()
    print("初始化完成，启动系统监控")

    # 扫描 hwmon 设备（调试风扇）
    for d in glob.glob('/sys/class/hwmon/hwmon*'):
        try:
            name = open(f'{d}/name').read().strip()
            fans = glob.glob(f'{d}/fan*_input')
            if fans:
                print(f"  hwmon 设备: {name}  -> {fans}")
        except:
            pass

    cpu_history = []

    net_iface = detect_net_iface()
    prev_rx, prev_tx = read_net_bytes(net_iface)
    net_ip = get_ip_address(net_iface)
    get_cpu_usage()  # 预热，建立 CPU 采样基准

    # 视图状态：'menu' 首页 / 'dashboard' / 'clock' / 'services' / 'music'
    view = 'clock'
    menu_cursor = 0
    shutdown_confirm = False
    clock_theme = 'dark'        # 翻页时钟主题：'dark' / 'light'
    services_cursor = 0
    services_scroll = 0
    detail_name = ''            # 当前详情页对应的服务名
    detail_action = 0           # 详情页操作按钮光标（见 SVC_ACTIONS）
    detail_focus = 'action'     # 焦点区域：'action' 按钮区 / 'log' 日志区
    detail_scroll = 0           # 日志滚动偏移
    detail_msg = ''             # 详情页操作结果提示
    detail_sampler = None       # 详情页状态/日志后台采样器
    action_state = {'pending': False, 'done': False, 'msg': ''}  # 控制操作线程结果
    update_state = {'running': False, 'lines': [], 'done': False, 'success': False, 'restarting': False}
    music_cursor = 0
    music_scroll = 0
    music_playing_index = -1
    music_songs = []
    music_loading = False
    keys = KeyReader()
    player = MusicPlayer()
    music_sampler = None  # 进入音乐页时再懒加载歌单
    camera_sampler = None # 摄像头帧采样器（进入摄像头页时启动）
    print("九宫格菜单：↑↓←→选择，Enter 进入，Esc 返回，q 退出")

    # WiFi 采集放到后台线程，避免 nmcli 扫描阻塞主循环
    wifi_sampler = BackgroundSampler(get_wifi_info, 8.0, initial=('', 0, 0))
    wifi_sampler.start()

    # 系统服务采集放到后台线程（每 30 秒刷新一次）
    services_sampler = BackgroundSampler(get_services, 30.0, initial=[], eager=True)
    services_sampler.start()

    # 采样数据初值（首帧渲染用）
    cpu = 0.0
    cpu_temp = None
    fan_val = fan_unit = None
    mem_used = mem_total = mem_pct = 0
    wifi_ssid, wifi_dbm, wifi_q = '', 0, 0
    net_down = net_up = 0
    services_data = services_sampler.get()

    last_sample = 0.0
    need_render = True

    def play_song(i):
        """播放第 i 首并记录为当前曲目；成功返回 True"""
        nonlocal music_playing_index
        song = music_songs[i]
        dur = song.get('duration', 0) / 1000.0
        if player.play(get_song_url(song['id']), dur):
            music_playing_index = i
            print(f"[音乐] 播放: {song['name']} - {song['artist']}")
            return True
        return False

    def run_action(name, act):
        """后台线程执行 systemctl 操作，结果写回 action_state，避免阻塞主循环"""
        ok, m = control_service(name, act)
        action_state['msg'] = m
        action_state['pending'] = False
        action_state['done'] = True
        print(f"[服务] {name} {act}: {'成功' if ok else '失败'} {m}")

    def _do_toggle_autostart(name):
        """后台线程切换自启状态"""
        ok, m = toggle_autostart(name)
        action_state['msg'] = m
        action_state['pending'] = False
        action_state['done'] = True
        print(f"[服务] {name} 自启切换: {'成功' if ok else '失败'} {m}")

    def do_update():
        """后台线程：git pull → 重启服务"""
        nonlocal update_state
        import subprocess as _sp
        update_state['running'] = True
        update_state['lines'] = ['正在拉取更新...']
        cwd = os.path.dirname(os.path.abspath(__file__))
        try:
            _sp.run(['git', 'config', '--global', '--add', 'safe.directory', cwd],
                    capture_output=True, text=True, timeout=10)
            r = _sp.run(['git', 'pull', 'https://github.com/zhanghan-cdns/st7789-TFT.git'],
                        capture_output=True, text=True, timeout=30, cwd=cwd)
            out = (r.stdout or '').strip()
            err = (r.stderr or '').strip()
            if out:
                update_state['lines'].append(out)
            if r.returncode == 0:
                update_state['lines'].append('拉取完成 ✓')
                update_state['success'] = True
            else:
                update_state['lines'].append(f'拉取失败: {err or out}')
                update_state['success'] = False
        except Exception as e:
            update_state['lines'].append(f'错误: {str(e)}')
            if hasattr(e, 'stderr') and e.stderr:
                update_state['lines'].append(str(e.stderr))
            update_state['success'] = False
        if update_state['success']:
            update_state['lines'].append('正在重启服务...')
            update_state['restarting'] = True
            try:
                _sp.run(['sudo', 'systemctl', 'restart', 'st7789-screen.service'], timeout=10)
            except Exception:
                pass
        update_state['done'] = True
        update_state['running'] = False

    try:
        while True:
            # 每秒采样一次系统信息（与页面无关，保持历史与日志连续）
            if time.monotonic() - last_sample >= 1.0:
                last_sample = time.monotonic()
                cpu = get_cpu_usage()
                cpu_history.append(cpu)
                if len(cpu_history) > CPU_HISTORY_LEN:
                    cpu_history.pop(0)
                cpu_temp = get_cpu_temp()
                fan_val, fan_unit = get_fan_rpm()
                mem_used, mem_total, mem_pct = get_memory()
                wifi_ssid, wifi_dbm, wifi_q = wifi_sampler.get()

                # 刷新服务数据（后台线程每 30 秒自动更新）
                services_data = services_sampler.get()

                rx, tx = read_net_bytes(net_iface)
                net_down = rx - prev_rx
                net_up = tx - prev_tx
                prev_rx, prev_tx = rx, tx

                temp_s = f"{cpu_temp:.0f}C" if cpu_temp is not None else "N/A"
                print(f"CPU: {cpu:.1f}%  MEM: {mem_pct:.1f}%  TEMP: {temp_s}  "
                      f"FAN: {fan_val}{fan_unit or ''}  WiFi: {wifi_ssid} "
                      f"NET ↓{net_down//1024}K ↑{net_up//1024}K")
                if view != 'menu':
                    need_render = True  # 子页每秒刷新（菜单页保持静态）

            # 音乐歌单后台懒加载：raw 为 None 表示尚未加载完成
            if music_sampler is not None:
                _raw = music_sampler.get()
                music_loading = _raw is None
                music_songs = _raw or []

            # 自动连播：当前曲目自然播放结束则切下一首
            if music_playing_index >= 0 and player.status() == 'stopped':
                nxt = music_playing_index + 1
                if nxt < len(music_songs):
                    play_song(nxt)
                    if view in ('music', 'playing'):
                        need_render = True
                else:
                    music_playing_index = -1

            # 服务控制操作完成：取回提示文本并刷新详情页
            if action_state['done']:
                action_state['done'] = False
                detail_msg = action_state['msg']
                if view == 'service_detail':
                    need_render = True
                    services_data = get_services()

            if need_render:
                if view == 'menu':
                    draw_menu(disp, MENU_ITEMS, menu_cursor)
                    if shutdown_confirm:
                        W, H = disp.width, disp.height
                        bw, bh = 200, 80
                        bx, by = (W - bw) // 2, (H - bh) // 2
                        disp.fill_round_rect(bx, by, bw, bh, 8, 0x0841)
                        disp.fill_round_rect(bx + 2, by + 2, bw - 4, bh - 4, 7, 0x2104)
                        disp.draw_text_pil(W // 2 - 36, by + 12, "确认关机?", 0xFFFF, size=18)
                        disp.draw_text_pil(W // 2 - 50, by + 45, "Enter确认  Esc取消", 0x8410, size=12)
                        disp.flush()
                elif view == 'dashboard':
                    draw_dashboard(disp, cpu, cpu_history, cpu_temp, fan_val, fan_unit,
                                   mem_used, mem_total, mem_pct,
                                   wifi_ssid, wifi_dbm, wifi_q,
                                   net_down, net_up, net_ip)
                elif view == 'clock':
                    lt = time.localtime()
                    draw_clock(disp,
                               time.strftime('%H:%M:%S', lt),
                               time.strftime('%Y-%m-%d', lt),
                               WEEKDAYS[lt.tm_wday],
                               lunar_date_str(lt.tm_year, lt.tm_mon, lt.tm_mday),
                               lunar_yi_yi_str(lt.tm_year, lt.tm_mon, lt.tm_mday),
                               theme=clock_theme)
                elif view == 'services':
                    draw_services(disp, services_data, services_cursor, services_scroll)
                elif view == 'service_detail':
                    detail = detail_sampler.get() if detail_sampler else None
                    draw_service_detail(disp, detail, detail_action, detail_msg,
                                       detail_focus, detail_scroll)
                elif view == 'music':
                    draw_music(disp, music_songs, music_cursor, music_scroll,
                               music_playing_index, player.status(), music_loading)
                elif view == 'playing':
                    cur_song = (music_songs[music_playing_index]
                                if 0 <= music_playing_index < len(music_songs)
                                else {})
                    draw_now_playing(disp, cur_song, player.status(),
                                     player.elapsed(), player.duration())
                elif view == 'camera':
                    frame = camera_sampler.get() if camera_sampler else None
                    draw_camera(disp, frame)
                elif view == 'update':
                    W, H = disp.width, disp.height
                    disp.fill_screen(0)
                    disp.fill_round_rect(6, 6, W - 12, 28, 6, 0x3186)
                    disp.draw_text_pil(16, 11, "系统更新", 0xFFFF, size=16)
                    y = 50
                    lines = update_state.get('lines', [])
                    for ln in lines:
                        if y > H - 30:
                            break
                        for sub in ln.split('\n'):
                            if y > H - 30:
                                break
                            clr = 0xFFFF if '失败' not in sub else 0xF800
                            disp.draw_text_pil(12, y, sub[:60], clr, size=12)
                            y += 18
                    if update_state['running'] and not update_state['done']:
                        dots = '.' * (int(time.monotonic() * 4) % 4)
                        disp.draw_text_pil(12, y, f"执行中{dots}", 0x8410, size=12)
                    elif update_state['done']:
                        disp.draw_text_pil(12, y + 4, "按 Esc 返回", 0x8410, size=12)
                    disp.flush()
                need_render = False

            # 摄像头页 / 更新页需要高频刷新
            if view == 'camera':
                need_render = True
            if view == 'update' and update_state['running']:
                need_render = True

            # 细粒度轮询按键，使切换即时响应
            key = keys.poll(0.05)
            if key is None:
                continue

            # ---------- 关机确认（优先于菜单，让 Esc 能取消） ----------
            if shutdown_confirm:
                if key == 'enter':
                    print("[菜单] 关机...")
                    import subprocess
                    subprocess.run(['sudo', 'poweroff'], timeout=5)
                    break
                elif key in ('back', 'quit'):
                    shutdown_confirm = False
                    need_render = True
                    continue
                continue

            # ---------- 菜单页 ----------
            if view == 'menu':
                if key in ('up', 'down', 'left', 'right'):
                    menu_cursor = move_cursor(menu_cursor, key, len(MENU_ITEMS))
                    need_render = True
                elif key == 'enter':
                    target = MENU_ITEMS[menu_cursor]['page']
                    if target == 'shutdown':
                        shutdown_confirm = True
                        need_render = True
                        continue
                    if target == 'update':
                        view = 'update'
                        update_state['lines'] = ['正在更新...']
                        update_state['done'] = False
                        update_state['running'] = True
                        update_state['success'] = False
                        update_state['restarting'] = False
                        threading.Thread(target=do_update, daemon=True).start()
                        need_render = True
                        continue
                    if target:
                        view = target
                        need_render = True
                        print(f"[菜单] 进入 {target}")
                        if target == 'music' and music_sampler is None:
                            music_sampler = BackgroundSampler(
                                get_hot_playlist, 600.0, initial=None)
                            music_sampler.start()
                        elif target == 'camera' and camera_sampler is None:
                            camera_sampler = CameraStream()
                            camera_sampler.start()
                elif key == 'quit':
                    break
                continue

            # ---------- 子页通用：Esc 返回（详情→列表，播放→列表，其余→菜单），q 退出 ----------
            if key == 'back':
                if view == 'playing':
                    view = 'music'
                elif view == 'service_detail':
                    view = 'services'
                    detail_focus = 'action'
                    detail_scroll = 0
                    if detail_sampler is not None:
                        detail_sampler.stop()
                        detail_sampler = None
                elif view == 'camera':
                    view = 'menu'
                    if camera_sampler is not None:
                        camera_sampler.stop()
                        camera_sampler = None
                elif view == 'clock':
                    draw_clock._prev = None
                    view = 'menu'
                else:
                    view = 'menu'
                need_render = True
                continue
            if key == 'quit':
                break

            # ---------- 时钟页：Enter 切换深/浅主题 ----------
            if view == 'clock':
                if key == 'enter':
                    clock_theme = 'light' if clock_theme == 'dark' else 'dark'
                    need_render = True

            # ---------- 系统服务页 ----------
            if view == 'services':
                if key == 'up' and services_cursor > 0:
                    services_cursor -= 1
                    if services_cursor < services_scroll:
                        services_scroll = services_cursor
                    need_render = True
                elif key == 'down' and services_data and \
                        services_cursor < len(services_data) - 1:
                    services_cursor += 1
                    if services_cursor >= services_scroll + SVC_ROWS:
                        services_scroll = services_cursor - SVC_ROWS + 1
                    need_render = True
                elif key == 'enter' and services_data:
                    # 进入服务详情页，启动后台采样（状态+日志，每 2 秒刷新）
                    detail_name = services_data[services_cursor][0]
                    detail_action = 0
                    detail_focus = 'action'
                    detail_scroll = 0
                    detail_msg = ''
                    if detail_sampler is not None:
                        detail_sampler.stop()
                    detail_sampler = BackgroundSampler(
                        lambda n=detail_name: get_service_status(n), 2.0,
                        initial=None)
                    detail_sampler.start()
                    view = 'service_detail'
                    need_render = True
                    print(f"[服务] 查看详情 {detail_name}")

            # ---------- 系统服务详情页 ----------
            elif view == 'service_detail':
                detail = detail_sampler.get() if detail_sampler else None
                detail_active = detail.get('active', '') if detail else ''
                svc_actions = get_actions(detail_active)
                n_actions = len(svc_actions)
                n_total = n_actions + 1  # +1 自启开关
                if key in ('left', 'right'):
                    if key == 'left':
                        detail_action = (detail_action - 1) % n_total
                    else:
                        detail_action = (detail_action + 1) % n_total
                    detail_scroll = 0
                    need_render = True
                elif key in ('up', 'down'):
                    LOG_PAGE = 5
                    if key == 'up' and detail_scroll > 0:
                        detail_scroll = max(0, detail_scroll - LOG_PAGE)
                        need_render = True
                    elif key == 'down':
                        max_scroll = max(0, len(detail_sampler.get().get('logs', [])) - 1) if detail_sampler and detail_sampler.get() else 0
                        if detail_scroll < max_scroll:
                            detail_scroll = min(detail_scroll + LOG_PAGE, max_scroll)
                            need_render = True
                elif key == 'enter' and not action_state['pending']:
                    action_state['pending'] = True
                    action_state['done'] = False
                    detail_msg = '执行中...'
                    if detail_action < n_actions:
                        act = svc_actions[detail_action][0]
                        threading.Thread(target=run_action,
                                         args=(detail_name, act),
                                         daemon=True).start()
                    else:
                        threading.Thread(target=lambda:
                            _do_toggle_autostart(detail_name),
                                         daemon=True).start()
                    need_render = True

            # ---------- 音乐列表页 ----------
            elif view == 'music':
                if key == 'up' and music_cursor > 0:
                    music_cursor -= 1
                    if music_cursor < music_scroll:
                        music_scroll = music_cursor
                    need_render = True
                elif key == 'down' and music_songs and \
                        music_cursor < len(music_songs) - 1:
                    music_cursor += 1
                    if music_cursor >= music_scroll + MUSIC_ROWS:
                        music_scroll = music_cursor - MUSIC_ROWS + 1
                    need_render = True
                elif key == 'enter' and music_songs:
                    play_song(music_cursor)
                    view = 'playing'  # 跳转到正在播放页
                    need_render = True

            # ---------- 正在播放页 ----------
            elif view == 'playing':
                if key == 'enter':
                    player.toggle_pause()
                    need_render = True
                elif key == 'left' and music_playing_index > 0:
                    play_song(music_playing_index - 1)
                    need_render = True
                elif key == 'right' and \
                        music_playing_index < len(music_songs) - 1:
                    play_song(music_playing_index + 1)
                    need_render = True
    except KeyboardInterrupt:
        pass
    finally:
        wifi_sampler.stop()
        services_sampler.stop()
        if detail_sampler is not None:
            detail_sampler.stop()
        if music_sampler is not None:
            music_sampler.stop()
        if camera_sampler is not None:
            camera_sampler.stop()
        player.stop()
        keys.restore()
        disp.close()
        print("程序退出")


if __name__ == "__main__":
    main()
