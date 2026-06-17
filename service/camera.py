"""摄像头帧采集：通过 ffmpeg 抓单帧，输出 RGB565 原始数据。"""
import subprocess


def capture_frame(device='/dev/video0', width=320, height=240):
    """从摄像头抓一帧，返回 raw RGB565 bytes 或 None。"""
    try:
        r = subprocess.run(
            ['ffmpeg', '-f', 'v4l2',
             '-video_size', f'{width}x{height}',
             '-i', device,
             '-vframes', '1',
             '-f', 'rawvideo',
             '-pix_fmt', 'rgb565',
             '-loglevel', 'error',
             '-'],
            capture_output=True, timeout=5)
        return r.stdout if r.stdout else None
    except Exception:
        return None
