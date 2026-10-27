import os
import asyncio
import aiohttp
import yt_dlp
from app.config import settings

AUDIO_DIR = "./data/audio"


def _download_audio_sync(bvid: str) -> str:
    """同步函数：使用 yt-dlp 下载B站视频音频"""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    url = f"https://www.bilibili.com/video/{bvid}"
    output_path = os.path.join(AUDIO_DIR, f"{bvid}")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_path}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        # 如果系统有ffmpeg，自动转码为m4a（兼容性最好）
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
            'preferredquality': '192',
        }] if _has_ffmpeg() else [],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # 确定实际文件路径
        downloaded = ydl.prepare_filename(info)
        # 如果有postprocessor，扩展名会被改为m4a
        if _has_ffmpeg():
            base, _ = os.path.splitext(downloaded)
            m4a_path = base + ".m4a"
            if os.path.exists(m4a_path):
                return m4a_path
        return downloaded


def _has_ffmpeg() -> bool:
    """检查系统是否安装了ffmpeg"""
    import shutil
    return shutil.which("ffmpeg") is not None


def _is_audio_supported(filepath: str) -> bool:
    """检查文件扩展名是否在Whisper API支持列表中"""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in ('.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.ogg')


async def transcribe_video_audio(bvid: str) -> str:
    """
    下载视频音频并调用Whisper API转录为文本
    返回转录文本，失败返回空字符串
    """
    filepath = None
    try:
        print(f"[Transcribe] 开始下载音频: {bvid}")
        filepath = await asyncio.to_thread(_download_audio_sync, bvid)

        if not os.path.exists(filepath):
            print(f"[Transcribe] 音频下载失败: {bvid}")
            return ""

        # 如果没有ffmpeg且格式不支持，尝试重命名（部分情况可用）
        if not _is_audio_supported(filepath):
            print(f"[Transcribe] 音频格式不支持，尝试跳过: {filepath}")
            # 如果系统没有ffmpeg，yt-dlp可能下载了m4s等格式，直接尝试读取上传
            # 有些服务商支持更多格式，先尝试上传

        print(f"[Transcribe] 音频已下载: {filepath} ({os.path.getsize(filepath)} bytes)")

        # 调用 Whisper API
        api_key = settings.WHISPER_API_KEY or settings.LLM_API_KEY
        base_url = settings.WHISPER_BASE_URL
        model = settings.WHISPER_MODEL

        if not api_key:
            print("[Transcribe] 错误：未配置 WHISPER_API_KEY 或 LLM_API_KEY")
            return ""

        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}

        # 读取文件并构造multipart请求
        with open(filepath, "rb") as audio_file:
            data = aiohttp.FormData()
            data.add_field("file", audio_file, filename=os.path.basename(filepath))
            data.add_field("model", model)
            data.add_field("language", "zh")
            data.add_field("response_format", "text")

            timeout = aiohttp.ClientTimeout(total=300)  # 转录可能较慢
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, data=data) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        print(f"[Transcribe] API错误 {resp.status}: {err_text[:300]}")
                        return ""

                    text = await resp.text()
                    print(f"[Transcribe] 转录完成: {bvid}, 长度 {len(text)} 字符")
                    return text.strip()

    except Exception as e:
        print(f"[Transcribe] 转录异常 {bvid}: {e}")
        return ""
    finally:
        # 清理临时音频文件
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"[Transcribe] 已清理临时文件: {filepath}")
            except Exception:
                pass
