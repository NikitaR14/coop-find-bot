from dataclasses import dataclass

import aiohttp

try:
    from config import settings
    from models.profile import Profile
except ModuleNotFoundError:
    from src.config import settings
    from src.models.profile import Profile


@dataclass(slots=True)
class DeliveryResult:
    delivered: bool
    reason: str | None = None


def reply_instruction(profile: Profile, request_id: int) -> str:
    if profile.platform == "discord":
        return f"/reply request_id:{request_id} message:ваш текст"
    return f"/reply {request_id} ваш текст"


def rate_instruction(profile: Profile, request_id: int) -> str:
    if profile.platform == "discord":
        return f"/rate request_id:{request_id}"
    return f"/rate {request_id}"


def accept_instruction(profile: Profile, request_id: int) -> str:
    if profile.platform == "discord":
        return f"/accept request_id:{request_id}"
    return f"/accept {request_id}"


async def deliver_text(profile: Profile, text: str) -> DeliveryResult:
    """Deliver through the transport that owns the target profile."""
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if profile.platform == "telegram":
                if not settings.TOKEN:
                    return DeliveryResult(False, "Telegram token is not configured")
                async with session.post(
                    f"https://api.telegram.org/bot{settings.TOKEN}/sendMessage",
                    json={
                        "chat_id": profile.user_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                ) as response:
                    payload = await response.json()
                    return DeliveryResult(
                        bool(payload.get("ok")), payload.get("description")
                    )

            if profile.platform == "discord":
                if not settings.DISCORD_TOKEN:
                    return DeliveryResult(False, "Discord token is not configured")
                headers = {
                    "Authorization": f"Bot {settings.DISCORD_TOKEN}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    "https://discord.com/api/v10/users/@me/channels",
                    headers=headers,
                    json={"recipient_id": str(profile.user_id)},
                ) as response:
                    if response.status >= 300:
                        return DeliveryResult(
                            False, f"Discord DM channel: HTTP {response.status}"
                        )
                    channel = await response.json()
                async with session.post(
                    f"https://discord.com/api/v10/channels/{channel['id']}/messages",
                    headers=headers,
                    json={"content": text, "allowed_mentions": {"parse": []}},
                ) as response:
                    return DeliveryResult(
                        response.status < 300,
                        None
                        if response.status < 300
                        else f"Discord DM: HTTP {response.status}",
                    )

            return DeliveryResult(False, f"Unknown platform: {profile.platform}")
    except (aiohttp.ClientError, TimeoutError) as exc:
        return DeliveryResult(False, str(exc))


async def deliver_telegram_rating_prompt(
    profile: Profile, text: str, request_id: int
) -> DeliveryResult:
    if profile.platform != "telegram" or not settings.TOKEN:
        return DeliveryResult(False, "Telegram delivery is not configured")
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Да ✅", "callback_data": f"rating_result:{request_id}:yes"},
                {
                    "text": "В процессе ⌛",
                    "callback_data": f"rating_result:{request_id}:waiting",
                },
                {"text": "Нет ❌", "callback_data": f"rating_result:{request_id}:no"},
            ]
        ]
    }
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"https://api.telegram.org/bot{settings.TOKEN}/sendMessage",
                json={
                    "chat_id": profile.user_id,
                    "text": text,
                    "reply_markup": keyboard,
                },
            ) as response:
                payload = await response.json()
                return DeliveryResult(
                    bool(payload.get("ok")), payload.get("description")
                )
    except (aiohttp.ClientError, TimeoutError) as exc:
        return DeliveryResult(False, str(exc))
