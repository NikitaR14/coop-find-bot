import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

try:
    from config import settings
    from google_sheet import GoogleSheetService
except ModuleNotFoundError:
    from src.config import settings
    from src.google_sheet import GoogleSheetService


logger = logging.getLogger("teamseek.discord.statistics")


@dataclass
class DiscordStatistics:
    """Best-effort Discord analytics in a worksheet separate from Telegram."""

    _service: GoogleSheetService | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    columns = {
        "filled_profile": 3,
        "start_search": 4,
        "open_profile": 5,
        "invite_game": 6,
        "website": 7,
        "last_activity": 8,
    }

    def _get_service(self) -> GoogleSheetService:
        if self._service is None:
            self._service = GoogleSheetService(
                credentials_path=settings.GOOGLE_SHEET_CREDENTIALS_PATH,
                sheet_id=settings.GOOGLE_SHEET_ID,
                worksheet=settings.DISCORD_STATS_WORKSHEET_NAME,
            )
        return self._service

    def _record_sync(self, user_id: int, username: str, event: str) -> None:
        service = self._get_service()
        if not service.worksheet.get_all_values():
            service.worksheet.append_row(
                [
                    "Discord ID",
                    "Discord Tag",
                    "Дата активации",
                    "Заполнил анкету",
                    "Начал поиск",
                    "Открыл анкету",
                    "Пригласил в игру",
                    "Нажал на сайт",
                    "Последний вход",
                ]
            )
        index = service.get_row_index(str(user_id), column=1)
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        if index is None:
            index = service.insert_row(
                [str(user_id), username, now, "-", "-", "-", "-", "-", now]
            )
        updates = {1: username, 8: now}
        if event in self.columns and event != "last_activity":
            updates[self.columns[event]] = "'+"
        service.update_row(index, updates)

    async def record(self, user_id: int, username: str, event: str) -> None:
        try:
            async with self._lock:
                await asyncio.to_thread(self._record_sync, user_id, username, event)
        except Exception:
            logger.exception(
                "Could not write Discord statistic %s for %s", event, user_id
            )


discord_statistics = DiscordStatistics()
