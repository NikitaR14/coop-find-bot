import asyncio
import logging

import discord

from .messages import send_temporary, followup_temporary, temporary_messages
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
    ClanAvatarModal,
    save_clan_avatar,
    GameSearchView,
    MenuView,
    MyProfileView,
    ProfileBasicsModal,
    ProfileDeleteConfirmView,
    PublicPanelView,
    LegacyPublicPanelView,
    RatingModal,
    RatingPromptView,
)


logger = logging.getLogger("teamseek.discord")


class TeamSeekBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.synced = False

    async def setup_hook(self) -> None:
        self.add_view(PublicPanelView())
        self.add_view(LegacyPublicPanelView())
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
        # Guild sync gives instant command updates only in an explicit test
        # guild. Production commands stay global so the bot remains installable
        # on other servers without duplicate entries in the primary guild.
        if settings.TEST_GUILD_ID:
            guild = discord.Object(id=settings.TEST_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        elif settings.PRIMARY_GUILD_ID:
            guild = discord.Object(id=settings.PRIMARY_GUILD_ID)
            self.tree.clear_commands(guild=guild)
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
        await temporary_messages.close()
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
        await send_temporary(
            interaction, "Основной Discord-сервер ещё не настроен.", ephemeral=True
        )
        return False
    guild = bot.get_guild(settings.PRIMARY_GUILD_ID)
    if guild is None:
        await send_temporary(
            interaction, "Бот не подключён к основному серверу.", ephemeral=True
        )
        return False
    try:
        member = guild.get_member(interaction.user.id) or await guild.fetch_member(
            interaction.user.id
        )
    except discord.NotFound:
        member = None
    except discord.HTTPException:
        await send_temporary(
            interaction,
            "Не удалось проверить членство на сервере. Попробуйте ещё раз.",
            ephemeral=True,
        )
        return False
    if member is None:
        await send_temporary(
            interaction,
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
    profile = await platform_repository.get_profile("discord", interaction.user.id)
    await send_temporary(
        interaction,
        "А кто это у нас такой красивый и до сих пор играет сам? Давай исправим это 🔍",
        view=MenuView(interaction.user.id, has_profile=profile is not None),
        ephemeral=True,
    )


@bot.tree.command(name="panel", description="Опубликовать панель TeamSeek в канале")
@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.describe(message_id="ID существующей панели в этом канале для обновления")
async def panel(
    interaction: discord.Interaction, message_id: str | None = None
) -> None:
    permissions = getattr(interaction.user, "guild_permissions", None)
    if not permissions or not permissions.manage_guild:
        await send_temporary(
            interaction,
            "Для публикации панели нужно право «Управлять сервером».",
            ephemeral=True,
        )
        return
    if not await primary_member(interaction):
        return
    if interaction.channel is None or not hasattr(interaction.channel, "send"):
        await send_temporary(
            interaction, "Не удалось определить канал для публикации.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    if message_id is not None:
        if (
            not 1 <= len(message_id) <= 20
            or not message_id.isascii()
            or not message_id.isdigit()
            or not 0 < int(message_id) < 2**64
        ):
            await followup_temporary(
                interaction, "Укажите корректный ID сообщения панели.", ephemeral=True
            )
            return
        try:
            message = await interaction.channel.fetch_message(int(message_id))

            # Recognise both original action rows and the newer V2 container.
            def panel_ids(components):
                for component in components:
                    custom_id = getattr(component, "custom_id", None)
                    if custom_id:
                        yield custom_id
                    yield from panel_ids(getattr(component, "children", ()))

            ids = set(panel_ids(message.components))
            if message.author.id != interaction.client.user.id or not ids.intersection(
                PublicPanelView.CUSTOM_IDS.values()
            ):
                await followup_temporary(
                    interaction,
                    "Это сообщение не является панелью TeamSeek этого бота.",
                    ephemeral=True,
                )
                return
            await message.edit(
                content=None, embeds=[], attachments=[], view=PublicPanelView()
            )
        except discord.HTTPException as exc:
            await followup_temporary(
                interaction, f"Не удалось обновить панель: {exc}", ephemeral=True
            )
            return
        await followup_temporary(
            interaction,
            "Панель TeamSeek обновлена. Закрепление сохранено.",
            ephemeral=True,
        )
        return
    try:
        message = await interaction.channel.send(view=PublicPanelView())
    except discord.HTTPException as exc:
        await followup_temporary(
            interaction, f"Не удалось опубликовать панель: {exc}", ephemeral=True
        )
        return
    try:
        await message.pin(reason=f"Панель TeamSeek опубликована {interaction.user}")
    except discord.HTTPException:
        await followup_temporary(
            interaction,
            "Панель опубликована, но закрепить её автоматически не удалось. "
            "Пожалуйста, закрепите сообщение вручную.",
            ephemeral=True,
        )
    else:
        await followup_temporary(
            interaction, "Панель TeamSeek опубликована и закреплена.", ephemeral=True
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
        await send_temporary(
            interaction, "Сначала создайте анкету командой `/form`.", ephemeral=True
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
        await send_temporary(
            interaction, "Анкета ещё не создана. Используйте `/form`.", ephemeral=True
        )
        return
    embed = profile_embed(current)
    photo_path = await resolve_profile_photo(current.photo, current.photo_origin)
    if photo_path:
        file = discord.File(photo_path, filename=photo_path.name)
        embed.set_image(url=f"attachment://{photo_path.name}")
        await send_temporary(
            interaction,
            embed=embed,
            file=file,
            view=MyProfileView(interaction.user.id, current),
            ephemeral=True,
        )
    else:
        await send_temporary(
            interaction,
            embed=embed,
            view=MyProfileView(interaction.user.id, current),
            ephemeral=True,
        )


@bot.tree.command(name="search", description="Поиск тиммейтов по игре")
@app_commands.guild_only()
async def search(interaction: discord.Interaction) -> None:
    if not await primary_member(interaction):
        return
    if not await platform_repository.get_profile("discord", interaction.user.id):
        await send_temporary(
            interaction, "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    await send_temporary(
        interaction,
        "Выберите игру:",
        view=GameSearchView(interaction.user.id, filtered=True),
        ephemeral=True,
    )


async def show_search(interaction: discord.Interaction, *, filtered: bool) -> None:
    if not await primary_member(interaction):
        return
    if not await platform_repository.get_profile("discord", interaction.user.id):
        await send_temporary(
            interaction, "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    await send_temporary(
        interaction,
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
        await send_temporary(
            interaction, "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    await send_temporary(
        interaction,
        "Раздел кланов:",
        view=ClanHubView(interaction.user.id),
        ephemeral=True,
    )


@bot.tree.command(name="photo", description="Добавить или заменить фото анкеты")
@app_commands.describe(upload="JPG, PNG, WEBP или GIF до 10 МБ")
@app_commands.guild_only()
async def photo(interaction: discord.Interaction, upload: discord.Attachment) -> None:
    if not await primary_member(interaction):
        return
    if not await platform_repository.get_profile("discord", interaction.user.id):
        await send_temporary(
            interaction, "Сначала создайте анкету командой `/form`.", ephemeral=True
        )
        return
    content_type = upload.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        await send_temporary(
            interaction, "Загрузите изображение JPG, PNG, WEBP или GIF.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        reference = await store_image(
            await upload.read(), content_type, upload.filename
        )
    except ValueError as exc:
        await followup_temporary(interaction, str(exc), ephemeral=True)
        return
    await platform_repository.update_photo(
        "discord", interaction.user.id, reference, "local"
    )
    await followup_temporary(interaction, "Фото анкеты обновлено.", ephemeral=True)


@bot.tree.command(name="clan_photo", description="Добавить или заменить аватар клана")
@app_commands.describe(
    clan_id="Номер вашей анкеты клана", upload="JPG, PNG, WEBP или GIF"
)
@app_commands.guild_only()
async def clan_photo(
    interaction: discord.Interaction,
    clan_id: int,
    upload: discord.Attachment | None = None,
) -> None:
    if not await primary_member(interaction):
        return
    if upload is None:
        await interaction.response.send_modal(ClanAvatarModal(clan_id))
        return
    await save_clan_avatar(interaction, clan_id, upload)


@bot.tree.command(name="pause", description="Снять анкету с поиска или вернуть её")
@app_commands.describe(active="Включить видимость анкеты")
@app_commands.guild_only()
async def pause(interaction: discord.Interaction, active: bool) -> None:
    if not await primary_member(interaction):
        return
    await platform_repository.set_profile_active("discord", interaction.user.id, active)
    await send_temporary(
        interaction,
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
        await send_temporary(interaction, "У вас нет анкеты.", ephemeral=True)
        return
    await send_temporary(
        interaction,
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
        await send_temporary(
            interaction,
            "Сообщение не найдено или принадлежит другому пользователю.",
            ephemeral=True,
        )
        return
    sender = await platform_repository.get_profile_by_id(request.sender_profile_id)
    if not sender:
        await send_temporary(interaction, "Анкета отправителя удалена.", ephemeral=True)
        return
    result = await deliver_text(
        sender,
        f"↩️ Ответ от {current.nickname} ({platform_badge(current.platform)})\n\n{message}",
    )
    await send_temporary(
        interaction,
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
        await send_temporary(interaction, "Сначала создайте анкету.", ephemeral=True)
        return
    applicant, awarded = await platform_repository.accept_clan_application(
        request_id, current.id
    )
    if not applicant:
        await send_temporary(
            interaction, "Заявка не найдена или уже закрыта.", ephemeral=True
        )
        return
    if awarded:
        await deliver_text(
            applicant,
            f"🏰 {current.nickname} принял вашу заявку в клан. Начислено 30 опыта.",
        )
    await send_temporary(
        interaction,
        "Заявка принята." if awarded else "Эта заявка уже была принята.",
        ephemeral=True,
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
        await send_temporary(interaction, "Приглашение не найдено.", ephemeral=True)
        return
    await interaction.response.send_modal(RatingModal(request_id))


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    logger.exception("Discord command failed", exc_info=error)
    message = "Произошла ошибка. Попробуйте ещё раз или вернитесь в `/menu`."
    if interaction.response.is_done():
        await followup_temporary(interaction, message, ephemeral=True)
    else:
        await send_temporary(interaction, message, ephemeral=True)


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
