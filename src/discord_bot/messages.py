"""Idle expiry for private replies; public panels and DMs stay persistent."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import discord

MESSAGE_TTL = 180
logger = logging.getLogger(__name__)


class TemporaryMessages:
    def __init__(self, *, sleep=asyncio.sleep):
        self._sleep = sleep
        self._tasks: dict[int, asyncio.Task] = {}

    def renew(self, message_id: int, delete: Callable[[], Awaitable[None]]) -> None:
        previous = self._tasks.pop(message_id, None)
        if previous is not None:
            previous.cancel()

        async def expire():
            try:
                await self._sleep(MESSAGE_TTL)
                await delete()
            except discord.NotFound:
                pass
            except Exception:
                logger.warning(
                    "Could not delete private message %s", message_id, exc_info=True
                )
            finally:
                if self._tasks.get(message_id) is asyncio.current_task():
                    self._tasks.pop(message_id, None)

        self._tasks[message_id] = asyncio.create_task(expire())

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


temporary_messages = TemporaryMessages()


def touch_temporary(interaction) -> None:
    """Use the latest interaction's webhook, including for select/modal activity."""
    message = getattr(interaction, "message", None)
    if (
        message is None
        or getattr(getattr(message, "flags", None), "ephemeral", False) is not True
    ):
        return
    temporary_messages.renew(
        message.id, lambda: interaction.followup.delete_message(message.id)
    )


async def send_temporary(interaction, *args, **kwargs):
    result = await interaction.response.send_message(*args, **kwargs)
    if kwargs.get("ephemeral"):
        message_id = result.message_id
        if message_id is None:
            message_id = (await interaction.original_response()).id
        temporary_messages.renew(message_id, interaction.delete_original_response)
    return result


async def followup_temporary(interaction, *args, **kwargs):
    # The first followup after a private defer inherits its ephemeral flag.
    kwargs["wait"] = True
    message = await interaction.followup.send(*args, **kwargs)
    if message.flags.ephemeral:
        temporary_messages.renew(message.id, message.delete)
    return message


async def edit_temporary(interaction, **kwargs):
    result = await interaction.response.edit_message(**kwargs)
    touch_temporary(interaction)
    return result
