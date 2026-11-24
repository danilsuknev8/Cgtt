import asyncio
import base64
import logging
import os
import re
import tempfile
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("9231872468:BOT_TOKEN")
MAX_TG_FILE_SIZE = 50 * 1024 * 1024  # Лимит Bot API — 50 МБ

# Не более 2 одновременных скачиваний, чтобы не упереться в 512 МБ RAM на Render Free
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(2)

COOKIE_ENV_MAP = {
    "instagram": ("INSTAGRAM_COOKIES_B64", "/tmp/instagram_cookies.txt", "/tmp/tiktok_cookies.txt"),
    "tiktok": ("TIKTOK_COOKIES_B64", "/tmp/tiktok_cookies.txt"),
    "youtube": ("YOUTUBE_COOKIES_B64", "/tmp/youtube_cookies.txt"),
    }

PLATFORM_NAMES = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube Shorts",
}

PLATFORM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "instagram",
        re.compile(
            r"https?://(?:www\.|m\.)?(?:instagram\.com|instagr\.am)/"
            r"(?:[\w.-]+/)?(?:reel|reels|p|tv|share)/[\w/-]+[^\s]*",
            re.IGNORECASE,
        ),
    ),
    (
        "tiktok",
        re.compile(
            r"https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+",
            re.IGNORECASE,
        ),
    ),
    (
        "youtube",
        re.compile(
            r"https?://(?:www\.|m\.)?youtube\.com/shorts/[\w-]+[^\s]*",
            re.IGNORECASE,
        ),
    ),
]

dp = Dispatcher()


def setup_cookies() -> dict[str, str]:
    """Декодирует cookies из переменных окружения для всех заданных платформ."""
    loaded: dict[str, str] = {}
    for platform, (env_name, file_path) in COOKIE_ENV_MAP.items():
        b64_data = os.getenv(env_name, "").strip()
        if not b64_data:
            continue
        try:
            Path(file_path).write_bytes(base64.b64decode(b64_data))
            loaded[platform] = file_path
            logger.info("Cookies для %s загружены.", platform)
        except Exception as exc:
            logger.error("Не удалось декодировать %s: %s", env_name, exc)
    return loaded


def detect_source(text: str) -> tuple[str, str] | None:
    """Определяет платформу и извлекает очищенную ссылку из текста сообщения."""
    for platform, pattern in PLATFORM_PATTERNS:
        match = pattern.search(text)
        if match:
            url = match.group(0).rstrip(".,)!?\"'>")
            return platform, url
    return None


def build_ydl_opts(platform: str, tmpdir: str, cookiefile: str | None) -> dict:
    """Формирует оптимальные параметры yt-dlp под конкретную платформу."""
    opts: dict = {
        "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        # H.264 + MP4 гарантирует корректное воспроизведение в Telegram на iOS и Android
        "format_sort": ["vcodec:h264", "res:1080", "ext:mp4:m4a"],
    }

    if platform == "tiktok":
        # Единый поток "b" у TikTok берет оригинальный файл воспроизведения без водяного знака
        opts["format"] = "b[ext=mp4]/bv*[ext=mp4]+ba[ext=m4a]/b"
    elif platform == "youtube":
        opts["format"] = "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/bv*+ba/b"
    else:
        opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
        opts["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        }

    if cookiefile and os.path.exists(cookiefile):
        opts["cookiefile"] = cookiefile

    return opts


def download_video(platform: str, url: str, tmpdir: str, cookiefile: str | None) -> dict:
    """Синхронное скачивание через yt-dlp (выполняется в отдельном потоке)."""
    ydl_opts = build_ydl_opts(platform, tmpdir, cookiefile)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("Не удалось получить данные о видео.")

        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        filepath = None
        if info.get("requested_downloads"):
            filepath = info["requested_downloads"][0].get("filepath")

        if not filepath or not os.path.exists(filepath):
            files = sorted(Path(tmpdir).glob("*"), key=lambda p: p.stat().st_size, reverse=True)
            if not files:
                raise RuntimeError("Файл видео не найден после загрузки.")
            filepath = str(files[0])

        return {
            "filepath": filepath,
            "width": info.get("width"),
            "height": info.get("height"),
            "duration": int(info["duration"]) if info.get("duration") else None,
        }


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Отправь ссылку на видео из:\n"
        "• Instagram (Reels / посты)\n"
        "• TikTok (без водяного знака)\n"
        "• YouTube Shorts"
    )


@dp.message(F.text)
async def handle_video_link(message: Message) -> None:
    detected = detect_source(message.text or "")
    if not detected:
        await message.answer(
            "Пришли ссылку на видео из Instagram, TikTok или YouTube Shorts."
        )
        return

    platform, url = detected
    platform_label = PLATFORM_NAMES[platform]

    if platform == "tiktok" and "/photo/" in url.lower():
        await message.answer(
            "Похоже, это фото-слайдшоу TikTok, а не видео — бот скачивает только видеоролики."
        )
        return

    status_msg = await message.answer(f"⏳ Скачиваю видео из {platform_label}...")
    cookie_path = COOKIE_ENV_MAP[platform][1]
    cookiefile = cookie_path if os.path.exists(cookie_path) else None

    try:
        async with DOWNLOAD_SEMAPHORE:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await asyncio.to_thread(
                    download_video, platform, url, tmpdir, cookiefile
                )
                file_size = os.path.getsize(result["filepath"])

                if file_size > MAX_TG_FILE_SIZE:
                    size_mb = file_size / (1024 * 1024)
                    await status_msg.edit_text(
                        f"Видео весит {size_mb:.1f} МБ — Telegram позволяет ботам отправлять файлы до 50 МБ."
                    )
                    return

                await status_msg.edit_text("📤 Отправляю в Telegram...")
                await message.answer_video(
                    video=FSInputFile(result["filepath"]),
                    width=result["width"],
                    height=result["height"],
                    duration=result["duration"],
                    supports_streaming=True,
                )
                await status_msg.delete()

    except yt_dlp.utils.DownloadError as exc:
        logger.warning("Ошибка yt-dlp (%s) для %s: %s", platform, url, exc)
        await status_msg.edit_text(
            f"Не удалось скачать видео из {platform_label}. "
            "Проверь, что ролик публичный и ссылка ведет именно на видео."
        )
    except Exception as exc:
        logger.exception("Непредвиденная ошибка (%s): %s", platform, exc)
        await status_msg.edit_text("Произошла ошибка при обработке видео. Попробуй позже.")


async def start_health_server() -> web.AppRunner:
    """HTTP-сервер для health-check и поддержания активности на Render."""
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="OK"))
    app.router.add_get("/health", lambda _: web.Response(text="OK"))

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health-сервер запущен на порту %s", port)
    return runner


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана.")

    setup_cookies()
    runner = await start_health_server()
    bot = Bot(token=BOT_TOKEN)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
