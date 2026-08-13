import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

try:
    from config import settings
    from services.delivery import deliver_text, deliver_telegram_rating_prompt
    from services.discord_statistics import discord_statistics
    from services.media import ALLOWED_IMAGE_TYPES, store_image, resolve_profile_photo
    from services.platform_repository import platform_repository
except ModuleNotFoundError:
    from src.config import settings
    from src.services.delivery import deliver_text, deliver_telegram_rating_prompt
    from src.services.discord_statistics import discord_statistics
    from src.services.media import (
        ALLOWED_IMAGE_TYPES,
        store_image,
        resolve_profile_photo,
    )
    from src.services.platform_repository import platform_repository

from .formatting import platform_badge, profile_embed
from .ui import (
    ClanHubView,
    GameSearchView,
    MenuView,
    ProfileBasicsModal,
    ProfileDeleteConfirmView,
    RatingModal,
    RatingPromptView,
)


logger = logging.getLogger("teamseek.discord")


class TeamSeekBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.synced = False

    async def setup_hook(self) -> None:
        for request in await platform_repository.active_rating_requests():
            sender = await platform_repository.get_profile_by_id(
                request.sender_profile_id
            )
            if sender and sender.platform == "discord":
                self.add_view(
                    RatingPromptView(
                        sender.user_id,
                        request.id,
                        in_process=request.status == "in_process",
                    )
                )
        self.reminder_worker.start()
        # Guild sync gives instant command updates during development. Global
        # sync keeps the bot installable on other servers as requested.
        if settings.TEST_GUILD_ID or settings.PRIMARY_GUILD_ID:
            guild_id = settings.TEST_GUILD_ID or settings.PRIMARY_GUILD_ID
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        await self.tree.sync()
        self.synced = True

    async def on_ready(self) -> None:
        logger.info(
            "Discord bot connected as %s (%s)",
            self.user,
            self.user.id if self.user else "?",
        )

    async def close(self) -> None:
        self.reminder_worker.cancel()
        await super().close()

    @tasks.loop(seconds=60)
    async def reminder_worker(self) -> None:
        requests = await platform_repository.due_contact_requests()
        for request in requests:
            sender = await platform_repository.get_profile_by_id(
                request.sender_profile_id
            )
            target = await platform_repository.get_profile_by_id(
                request.target_profile_id
            )
            if not sender or not target:
                await platform_repository.mark_contact_failed(request.id)
                continue
            if sender and target:
                text = (
                    f"Привет! Удалось ли сыграть с {target.nickname}?\n"
                    "Выберите результат:"
                )
                if sender.platform == "discord":
                    try:
                        user = self.get_user(sender.user_id) or await self.fetch_user(
                            sender.user_id
                        )
                        view = RatingPromptView(sender.user_id, request.id)
                        await user.send(text, view=view)
                        self.add_view(view)
                        delivered = True
                        reason = None
                    except discord.HTTPException as exc:
                        delivered = False
                        reason = str(exc)
                else:
                    result = await deliver_telegram_rating_prompt(
                        sender, text, request.id
                    )
                    delivered = result.delivered
                    reason = result.reason
                if delivered:
                    await platform_repository.mark_reminder_sent(request.id)
                else:
                    logger.warning(
                        "Reminder %s was not delivered: %s", request.id, reason
                    )

    @reminder_worker.before_loop
    async def before_reminders(self) -> None:
        await self.wait_until_ready()


bot = TeamSeekBot()


async def notify_level(user: discord.User | discord.Member, level: int) -> None:
    try:
        await user.send(f"Новый уровень! Теперь у вас {level} уровень ⚡")
    except discord.HTTPException:
        logger.info("Could not send level-up DM to %s", user.id)


async def primary_member(interaction: discord.Interaction) -> bool:
    if not settings.PRIMARY_GUILD_ID:
        await interaction.response.send_message(
            "Основной Discord-сервер ещё не настроен.", ephemeral=True
        )
        return False
    guild = bot.get_guild(settings.PRIMARY_GUILD_ID)
    if guild is None:
        await interaction.response.send_message(
            "Бот не подключён к основному серверу.", ephemeral=True
        )
        return False
    try:
        member = guild.get_member(interaction.user.id) or await guild.fetch_member(
            interaction.user.id
        )
    except discord.NotFound:
        member = None
    except discord.HTTPException:
        await interaction.response.send_message(
            "Не удалось проверить членство на сервере. Попробуйте ещё раз.",
            ephemeral=True,
        )
        return False
    if member is None:
        await interaction.response.send_message(
            "Функции TeamSeek доступны участникам основного сервера GG.Store.",
            ephemeral=True,
        )
        return False
    profile = await platform_repository.get_profile("discord", interaction.user.id)
    if profile:
        old_level, new_level, _ = await platform_repository.track_daily_activity(
            profile.id
        )
        if new_level > old_level:
            asyncio.create_task(notify_level(interaction.user, new_level))
    asyncio.create_task(
        discord_statistics.record(
            interaction.user.id, str(interaction.user), "last_activity"
        )
    )
    return True


@bot.tree.command(name="menu", description="Открыть приватное меню TeamSeek")
@app_commands.guild_only()
async def menu(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    await interaction.response.send_message(
        "А кто это у нас такой красивый и до сих пор играет сам? Давай исправим это 🔍",
        view=MenuView(interaction.user.id),
        ephemeral=True,
    )


@bot.tree.command(name="form", description="Создать или заполнить заново анкету игрока")
@app_commands.guild_only()
async def form(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    profile = await platform_repository.get_profile("discord", interaction.user.id)
    await interaction.response.send_modal(
        ProfileBasicsModal(interaction.user.id, profile)
    )


@bot.tree.command(name="edit", description="Изменить анкету игрока")
@app_commands.guild_only()
async def edit(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    profile = await platform_repository.get_profile("discord", interaction.user.id)
    if not profile:
        await interaction.response.send_message(
            "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    await interaction.response.send_modal(
        ProfileBasicsModal(interaction.user.id, profile)
    )


@bot.tree.command(name="profile", description="Показать свою анкету")
@app_commands.guild_only()
async def profile(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    current = await platform_repository.get_profile("discord", interaction.user.id)
    if not current:
        await interaction.response.send_message(
            "Анкета ещё не создана. Используйте `/form`.", ephemeral=True
        )
        return
    embed = profile_embed(current)
    photo_path = await resolve_profile_photo(current.photo, current.photo_origin)
    if photo_path:
        file = discord.File(photo_path, filename=photo_path.name)
        embed.set_image(url=f"attachment://{photo_path.name}")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="search", description="Поиск тиммейтов по игре")
@app_commands.guild_only()
async def search(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    if not await platform_repository.get_profile("discord", interaction.user.id):
        await interaction.response.send_message(
            "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    await interaction.response.send_message(
        "Выберите игру:",
        view=GameSearchView(interaction.user.id, filtered=True),
        ephemeral=True,
    )


async def show_search(interaction: discord.Interaction, *, filtered: bool) -> None:
    if not await primary_member(interaction):
        return
    if not await platform_repository.get_profile("discord", interaction.user.id):
        await interaction.response.send_message(
            "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    await interaction.response.send_message(
        "Выберите игру:",
        view=GameSearchView(interaction.user.id, filtered=filtered),
        ephemeral=True,
    )


@bot.tree.command(name="all", description="Показать все анкеты по выбранной игре")
@app_commands.guild_only()
async def all_profiles(interaction: discord.Interaction) -> None:
    await show_search(interaction, filtered=False)


@bot.tree.command(name="clan", description="Создание и поиск кланов")
@app_commands.guild_only()
async def clan(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    if not await platform_repository.get_profile("discord", interaction.user.id):
        await interaction.response.send_message(
            "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    await interaction.response.send_message(
        "Раздел кланов:", view=ClanHubView(interaction.user.id), ephemeral=True
    )


@bot.tree.command(name="photo", description="Добавить или заменить фото анкеты")
@app_commands.describe(upload="JPG, PNG, WEBP или GIF до 10 МБ")
@app_commands.guild_only()
async def photo(interaction: discord.Interaction, upload: discord.Attachment) -> None:
    if not await primary_member(interaction):
        return
    if not await platform_repository.get_profile("discord", interaction.user.id):
        await interaction.response.send_message(
            "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    content_type = upload.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        await interaction.response.send_message(
            "Загрузите изображение JPG, PNG, WEBP или GIF.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        reference = await store_image(
            await upload.read(), content_type, upload.filename
        )
    except ValueError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    await platform_repository.update_photo(
        "discord", interaction.user.id, reference, "local"
    )
    await interaction.followup.send("Фото анкеты обновлено.", ephemeral=True)


@bot.tree.command(name="clan_photo", description="Добавить или заменить аватар клана")
@app_commands.describe(
    clan_id="Номер вашей анкеты клана", upload="JPG, PNG, WEBP или GIF"
)
@app_commands.guild_only()
async def clan_photo(
    interaction: discord.Interaction, clan_id: int, upload: discord.Attachment
) -> None:
    if not await primary_member(interaction):
        return
    clan = await platform_repository.get_clan_by_id(clan_id)
    if not clan or clan.platform != "discord" or clan.user_id != interaction.user.id:
        await interaction.response.send_message(
            "Ваша анкета клана не найдена.", ephemeral=True
        )
        return
    content_type = upload.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        await interaction.response.send_message(
            "Загрузите изображение JPG, PNG, WEBP или GIF.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        reference = await store_image(
            await upload.read(), content_type, upload.filename
        )
    except ValueError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    await platform_repository.update_clan_photo(
        clan_id, "discord", interaction.user.id, reference, "local"
    )
    await interaction.followup.send("Аватар клана обновлён.", ephemeral=True)


@bot.tree.command(name="pause", description="Снять анкету с поиска или вернуть её")
@app_commands.describe(active="Включить видимость анкеты")
@app_commands.guild_only()
async def pause(interaction: discord.Interaction, active: bool) -> None:
    if not await primary_member(interaction):
        return
    await platform_repository.set_profile_active("discord", interaction.user.id, active)
    await interaction.response.send_message(
        "Анкета размещена в поиске." if active else "Анкета снята с поиска.",
        ephemeral=True,
    )


@bot.tree.command(
    name="delete_profile", description="Удалить свою анкету и связанные данные"
)
@app_commands.guild_only()
async def delete_profile(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    current = await platform_repository.get_profile("discord", interaction.user.id)
    if not current:
        await interaction.response.send_message("У вас нет анкеты.", ephemeral=True)
        return
    await interaction.response.send_message(
        "Точно удалить анкету и связанные данные?",
        view=ProfileDeleteConfirmView(interaction.user.id),
        ephemeral=True,
    )


@bot.tree.command(name="reply", description="Ответить на приглашение или сообщение")
@app_commands.describe(
    request_id="Номер из входящего сообщения", message="Текст ответа"
)
@app_commands.guild_only()
async def reply(
    interaction: discord.Interaction, request_id: int, message: str
) -> None:
    if not await primary_member(interaction):
        return
    current = await platform_repository.get_profile("discord", interaction.user.id)
    request = await platform_repository.get_contact_request(request_id)
    if not current or not request or request.target_profile_id != current.id:
        await interaction.response.send_message(
            "Сообщение не найдено или принадлежит другому пользователю.", ephemeral=True
        )
        return
    sender = await platform_repository.get_profile_by_id(request.sender_profile_id)
    if not sender:
        await interaction.response.send_message(
            "Анкета отправителя удалена.", ephemeral=True
        )
        return
    result = await deliver_text(
        sender,
        f"↩️ Ответ от {current.nickname} ({platform_badge(current.platform)})\n\n{message}",
    )
    await interaction.response.send_message(
        "Ответ отправлен." if result.delivered else "Не удалось доставить ответ.",
        ephemeral=True,
    )


@bot.tree.command(name="accept", description="Принять заявку игрока в клан")
@app_commands.describe(request_id="Номер заявки из входящего сообщения")
@app_commands.guild_only()
async def accept(interaction: discord.Interaction, request_id: int) -> None:
    if not await primary_member(interaction):
        return
    current = await platform_repository.get_profile("discord", interaction.user.id)
    if not current:
        await interaction.response.send_message(
            "Сначала создайте анкету.", ephemeral=True
        )
        return
    applicant, awarded = await platform_repository.accept_clan_application(
        request_id, current.id
    )
    if not applicant:
        await interaction.response.send_message(
            "Заявка не найдена или уже закрыта.", ephemeral=True
        )
        return
    if awarded:
        await deliver_text(
            applicant,
            f"🏰 {current.nickname} принял вашу заявку в клан. Начислено 30 опыта.",
        )
    await interaction.response.send_message(
        "Заявка принята." if awarded else "Эта заявка уже была принята.", ephemeral=True
    )


@bot.tree.command(name="rate", description="Оценить тиммейта после совместной игры")
@app_commands.describe(request_id="Номер приглашения из напоминания")
@app_commands.guild_only()
async def rate(interaction: discord.Interaction, request_id: int) -> None:
    if not await primary_member(interaction):
        return
    request = await platform_repository.get_contact_request(request_id)
    current = await platform_repository.get_profile("discord", interaction.user.id)
    if not request or not current or request.sender_profile_id != current.id:
        await interaction.response.send_message(
            "Приглашение не найдено.", ephemeral=True
        )
        return
    await interaction.response.send_modal(RatingModal(request_id))


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    logger.exception("Discord command failed", exc_info=error)
    message = "Произошла ошибка. Попробуйте ещё раз или вернитесь в `/menu`."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def main() -> None:
    if not settings.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not configured")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    async with bot:
        await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
