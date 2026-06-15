# ST7789 系统监控仪表盘

基于 Python 的 ST7789 SPI 显示屏驱动，在**鲁班猫3 / RK3576** 上实时显示系统监控数据（CPU、内存、WiFi）。

## 接线（鲁班猫3 / RK3576）

| ST7789 | 鲁班猫3 物理引脚 | 说明 |
|--------|:---------------:|------|
| SCL    | 23 | SPI 时钟 |
| SDA    | 19 | SPI MOSI |
| CS     | 24 | SPI CS0（spidev1.0 硬件控制） |
| RES    | 29 | 复位 |
| DC     | 31 | 数据/命令 |

## 依赖安装

```bash
sudo apt install python3-pip
sudo pip3 install spidev gpiod --break-system-packages
```

> 若需 WiFi 信息，还需确保 `nmcli`（默认安装）或 `iw` 可用。

## 启动

```bash
sudo python3 main.py
```

> 需要 `sudo` 权限以访问 SPI 和 GPIO 设备。

按 `Ctrl+C` 退出程序。

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 主入口，采集系统信息 + 主循环 |
| `st7789_driver.py` | ST7789 底层驱动，SPI/GPIO 控制 + 帧缓冲 + 字体 |
| `ui.py` | UI 渲染，进度条、WiFi 图标、仪表盘布局 |

## 显示内容

- CPU 使用率（百分比 + 进度条）
- CPU 温度
- 内存（已用/总量 + 进度条）
- WiFi 信号（SSID、dBm、信号强度图标）

## 参数调整

若屏幕花屏或方向不对，可在 `st7789_driver.py` 的 `init()` 方法中调整：

- **镜像方向**：第 185 行 `self._data(0x20)`，可试 `0x60` / `0xA0` / `0xE0`
- **SPI 模式**：`ST7789(spi_mode=3)`，花屏可改为 `0`

## 故障排查

| 现象 | 检查点 |
|------|--------|
| 白屏/花屏 | 确认接线正确；调整 `spi_mode` 或 MADCTL 值 |
| 报 SPI 错误 | `ls /dev/spidev*` 确认 SPI 已使能 |
| 报 GPIO 错误 | 确认 `rst_pin`/`dc_pin` 与实际 GPIO 编号一致 |
