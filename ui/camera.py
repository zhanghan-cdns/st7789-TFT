"""摄像头画面显示"""
from color import BLACK, WHITE, DGRAY, LGRAY


def draw_camera(disp, frame, name=''):
    """将 raw RGB565 帧数据直接写入显示帧缓冲并刷新。

    参数：
      frame — ffmpeg 输出的 raw RGB565 bytes，宽×高×2
      name  — 顶部显示的摄像头名称（可选）
    """
    W = disp.width
    H = disp.height
    expected = W * H * 2

    disp.fill_screen(BLACK)

    if not frame or len(frame) < expected:
        text = "摄像头不可用" if frame is None else "帧数据不完整"
        disp.draw_text_pil(16, 110, text, DGRAY, size=14)
        hint = "请检查 /dev/video0   Esc 返回"
        disp.draw_text_pil(16, 140, hint, DGRAY, size=11)
        disp.flush()
        return

    disp.buf[:expected] = frame[:expected]

    if name:
        disp.fill_round_rect(6, 6, W - 12, 22, 6, 0x2104)
        disp.draw_text_pil(16, 10, name[:28], WHITE, size=12)

    hint = "Esc 返回"
    hw, _ = disp.text_size_pil(hint, 10)
    disp.draw_text_pil(W - 8 - hw, H - 14, hint, DGRAY, size=10)
    disp.flush()
