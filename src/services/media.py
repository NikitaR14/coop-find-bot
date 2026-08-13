from pathlib import Path
from uuid import uuid4

import aiohttp

try:
    from config import settings
except ModuleNotFoundError:
    from src.config import settings


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def media_root() -> Path:
    root = Path(settings.MEDIA_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


async def store_image(data: bytes, content_type: str, original_name: str) -> str:
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Поддерживаются JPG, PNG, WEBP и GIF")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Файл больше 10 МБ")
    suffix = Path(original_name).suffix.lower() or ".jpg"
    path = media_root() / f"{uuid4().hex}{suffix}"
    path.write_bytes(data)
    return str(path)


async def resolve_profile_photo(photo: str | None, origin: str | None) -> Path | None:
    if not photo:
        return None
    if origin in {"local", "discord"}:
        path = Path(photo)
        return path if path.is_file() else None
    if origin != "telegram" or not settings.TOKEN:
        return None

    cache_path = media_root() / "telegram" / photo.replace("/", "_")
    if cache_path.is_file():
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"https://api.telegram.org/bot{settings.TOKEN}/getFile",
            params={"file_id": photo},
        ) as response:
            payload = await response.json()
            if not payload.get("ok"):
                return None
            file_path = payload["result"]["file_path"]
        async with session.get(
            f"https://api.telegram.org/file/bot{settings.TOKEN}/{file_path}"
        ) as response:
            if response.status != 200:
                return None
            cache_path = cache_path.with_suffix(Path(file_path).suffix or ".jpg")
            cache_path.write_bytes(await response.read())
            return cache_path
