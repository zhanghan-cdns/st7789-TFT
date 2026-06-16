"""ST7789 系统监控主程序

负责系统信息采集与主循环，调度 st7789_driver 驱动和 ui 渲染。
运行：python main.py
"""
import time
import sys
import glob

from st7789_driver import ST7789
from ui import draw_dashboard, draw_clock, draw_services, lunar_date_str, CPU_HISTORY_LEN
from ui.services import ROWS_PER_PAGE
from service import (
    KeyReader, BackgroundSampler,
    get_cpu_usage, get_cpu_temp, get_fan_rpm, get_memory,
    get_wifi_info, get_ip_address, get_services,
    detect_net_iface, read_net_bytes,
)

# 页面：0=系统监控，1=时钟，2=系统服务
NUM_PAGES = 3
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

    # 多页状态与按键读取
    page = 0
    services_cursor = 0
    services_scroll = 0
    keys = KeyReader()
    print("← →切换页面（系统监控/时钟/系统服务），↑↓滚动服务列表，q 退出")

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
                need_render = True  # 数据更新触发重绘（时钟页借此每秒刷新）

            if need_render:
                if page == 0:
                    draw_dashboard(disp, cpu, cpu_history, cpu_temp, fan_val, fan_unit,
                                   mem_used, mem_total, mem_pct,
                                   wifi_ssid, wifi_dbm, wifi_q,
                                   net_down, net_up, net_ip)
                elif page == 1:
                    lt = time.localtime()
                    draw_clock(disp,
                               time.strftime('%H:%M:%S', lt),
                               time.strftime('%Y-%m-%d', lt),
                               WEEKDAYS[lt.tm_wday],
                               lunar_date_str(lt.tm_year, lt.tm_mon, lt.tm_mday))
                else:
                    draw_services(disp, services_data, services_cursor, services_scroll)
                need_render = False

            # 细粒度轮询按键，使切换即时响应
            key = keys.poll(0.05)
            if key == 'left':
                page = (page - 1) % NUM_PAGES
                need_render = True
                print(f"[按键] 左 -> 切换到页面 {page}")
            elif key == 'right':
                page = (page + 1) % NUM_PAGES
                need_render = True
                print(f"[按键] 右 -> 切换到页面 {page}")
            elif key == 'up':
                if page == 2 and services_cursor > 0:
                    services_cursor -= 1
                    if services_cursor < services_scroll:
                        services_scroll = services_cursor
                    print(f"[按键] 上 -> 光标 {services_cursor}")
                    need_render = True
            elif key == 'down':
                if page == 2 and services_data and services_cursor < len(services_data) - 1:
                    services_cursor += 1
                    if services_cursor >= services_scroll + ROWS_PER_PAGE:
                        services_scroll = services_cursor - ROWS_PER_PAGE + 1
                    print(f"[按键] 下 -> 光标 {services_cursor}")
                    need_render = True
            elif key == 'quit':
                break
    except KeyboardInterrupt:
        pass
    finally:
        wifi_sampler.stop()
        services_sampler.stop()
        keys.restore()
        disp.close()
        print("程序退出")


if __name__ == "__main__":
    main()
