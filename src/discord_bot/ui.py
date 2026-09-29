import asyncio
import logging
from dataclasses import dataclass, field

import aiohttp
import discord
from sqlalchemy.exc import SQLAlchemyError

from .messages import (
    send_temporary,
    followup_temporary,
    edit_temporary,
    touch_temporary,
)

try:
    from config import settings
    from services.delivery import accept_instruction, deliver_text, reply_instruction
    from services.discord_statistics import discord_statistics
    from services.media import (
        resolve_profile_photo,
        store_image,
        ALLOWED_IMAGE_TYPES,
        MAX_IMAGE_BYTES,
    )
    from services.platform_repository import platform_repository
    from utils.constants import (
        AION_2_FACTIONS,
        CONVENIENT_TIME,
        GAME_LIST,
        GENDER_LIST,
        GOALS_LIST,
    )
except ModuleNotFoundError:
    from src.config import settings
    from src.services.delivery import (
        accept_instruction,
        deliver_text,
        reply_instruction,
    )
    from src.services.discord_statistics import discord_statistics
    from src.services.media import (
        resolve_profile_photo,
        store_image,
        ALLOWED_IMAGE_TYPES,
        MAX_IMAGE_BYTES,
    )
    from src.services.platform_repository import platform_repository
    from src.utils.constants import (
        AION_2_FACTIONS,
        CONVENIENT_TIME,
        GAME_LIST,
        GENDER_LIST,
        GOALS_LIST,
    )

from .formatting import clan_embed, platform_badge, profile_embed

MMO_GAMES = {"Warcraft", "WoR", "AION 2"}


@dataclass(slots=True)
class ProfileDraft:
    nickname: str
    age: int | None
    about: str
    gender: str | None = None
    games: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    convenient_time: list[str] = field(default_factory=list)
    ranks: dict[str, str | None] = field(default_factory=dict)
    game_details: dict[str, dict[str, str | None]] = field(default_factory=dict)
    is_active: bool = True

    @classmethod
    def from_profile(cls, profile):
        return cls(
            nickname=profile.nickname,
            age=profile.age,
            about=profile.about,
            gender=profile.gender,
            games=[game.name for game in profile.games],
            goals=list(profile.goals or []),
            convenient_time=list(profile.convenient_time or []),
            ranks={game.name: game.rank for game in profile.games},
            game_details={
                game.name: {"server": game.server, "faction": game.faction}
                for game in profile.games
            },
            is_active=profile.is_active,
        )


class OwnedView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float | None = 900):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temporary(
                interaction,
                "Эта приватная панель принадлежит другому пользователю.",
                ephemeral=True,
            )
            return False
        touch_temporary(interaction)
        return True


class OwnedLayoutView(discord.ui.LayoutView):
    """Components V2 view that can only be used by its owner."""

    def __init__(self, owner_id: int, *, timeout: float | None = 900):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temporary(
                interaction,
                "Эта приватная панель принадлежит другому пользователю.",
                ephemeral=True,
            )
            return False
        touch_temporary(interaction)
        return True


class TemporaryModal(discord.ui.Modal):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        touch_temporary(interaction)
        return True


class ProfileBasicsModal(TemporaryModal, title="Анкета игрока"):
    nickname = discord.ui.TextInput(
        label="Никнейм",
        min_length=1,
        max_length=32,
        placeholder="Как тебя показывать в анкете",
    )
    age = discord.ui.TextInput(
        label="Возраст (необязательно)", required=False, min_length=1, max_length=3
    )
    about = discord.ui.TextInput(
        label="О себе", style=discord.TextStyle.paragraph, min_length=1, max_length=1000
    )

    def __init__(
        self, user_id: int, existing=None, *, draft: ProfileDraft | None = None
    ):
        super().__init__()
        self.user_id = user_id
        self.existing = existing
        self.draft = draft
        if draft:
            self.nickname.default = draft.nickname
            self.age.default = str(draft.age or "")
            self.about.default = draft.about
        if existing:
            self.nickname.default = existing.nickname
            self.age.default = str(existing.age or "")
            self.about.default = existing.about

    async def on_submit(self, interaction: discord.Interaction) -> None:
        age = None
        if self.age.value.strip():
            try:
                age = int(self.age.value)
            except ValueError:
                await send_temporary(
                    interaction, "Возраст должен быть числом.", ephemeral=True
                )
                return
            if age < 13 or age > 120:
                await send_temporary(
                    interaction, "Укажите возраст от 13 до 120 лет.", ephemeral=True
                )
                return
        draft = self.draft or (
            ProfileDraft.from_profile(self.existing)
            if self.existing
            else ProfileDraft(nickname="", age=None, about="")
        )
        draft.nickname = self.nickname.value.strip()
        draft.age = age
        draft.about = self.about.value.strip()
        if self.draft or self.existing:
            await send_profile_preview(interaction, draft)
            return
        await send_temporary(
            interaction,
            "Параметры анкеты: выберите игры, цели и удобное время.",
            view=ProfileOptionsView(interaction.user.id, draft),
            ephemeral=True,
        )


class DraftSelect(discord.ui.Select):
    def __init__(self, *, field_name: str, **kwargs):
        super().__init__(**kwargs)
        self.field_name = field_name

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        value = self.values[0] if self.max_values == 1 else list(self.values)
        if self.field_name == "gender" and value == "Не указан":
            value = None
        setattr(view.draft, self.field_name, value)
        await interaction.response.defer()


class ProfileOptionsView(OwnedView):
    def __init__(self, owner_id: int, draft: ProfileDraft):
        super().__init__(owner_id)
        self.draft = draft
        self.add_item(
            DraftSelect(
                field_name="gender",
                placeholder="Пол",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label=value, value=value)
                    for value in GENDER_LIST
                ]
                + [discord.SelectOption(label="Не указывать", value="Не указан")],
            )
        )
        self.add_item(
            DraftSelect(
                field_name="games",
                placeholder="Игры (до 5)",
                min_values=1,
                max_values=5,
                options=[
                    discord.SelectOption(label=name, value=name) for name in GAME_LIST
                ],
            )
        )
        self.add_item(
            DraftSelect(
                field_name="goals",
                placeholder="Цели поиска (до 5)",
                min_values=1,
                max_values=5,
                options=[
                    discord.SelectOption(label=value, value=value)
                    for value in GOALS_LIST
                ],
            )
        )
        self.add_item(
            DraftSelect(
                field_name="convenient_time",
                placeholder="Удобное время",
                min_values=1,
                max_values=len(CONVENIENT_TIME),
                options=[
                    discord.SelectOption(label=value, value=value)
                    for value in CONVENIENT_TIME
                ],
            )
        )
        for item in self.children:
            if isinstance(item, DraftSelect):
                current = getattr(draft, item.field_name)
                for option in item.options:
                    option.default = (
                        option.value in (current or [])
                        if isinstance(current, list)
                        else option.value == (current or "Не указан")
                    )

    @discord.ui.button(label="Продолжить", style=discord.ButtonStyle.success)
    async def continue_form(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if (
            not self.draft.games
            or not self.draft.goals
            or not self.draft.convenient_time
        ):
            await send_temporary(
                interaction,
                "Выберите хотя бы одну игру, цель поиска и удобное время.",
                ephemeral=True,
            )
            return
        self.draft.ranks = {
            game: self.draft.ranks.get(game) for game in self.draft.games
        }
        await edit_temporary(
            interaction,
            content="Игровые ранги: измените значения или продолжите с текущими.",
            view=ProfileRanksView(interaction.user.id, self.draft),
        )


class ProfileRanksView(OwnedView):
    def __init__(self, owner_id: int, draft: ProfileDraft):
        super().__init__(owner_id)
        self.draft = draft

    @discord.ui.button(label="Указать ранги", style=discord.ButtonStyle.success)
    async def specify(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(RanksModal(self.draft))

    @discord.ui.button(label="Пропустить ранги", style=discord.ButtonStyle.secondary)
    async def skip(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        self.draft.ranks = {
            game: self.draft.ranks.get(game) for game in self.draft.games
        }
        if "AION 2" in self.draft.games and not all(
            self.draft.game_details.get("AION 2", {}).get(key)
            for key in ("server", "faction")
        ):
            await edit_temporary(
                interaction,
                content="Для AION 2 выберите фракцию и укажите сервер:",
                view=AionProfileDetailsView(interaction.user.id, self.draft),
            )
            return
        await send_profile_preview(interaction, self.draft, edit=True)


class RanksModal(TemporaryModal, title="Ранги и уровни"):
    def __init__(self, draft: ProfileDraft):
        super().__init__()
        self.draft = draft
        self.rank_inputs: dict[str, discord.ui.TextInput] = {}
        for game in draft.games[:5]:
            item = discord.ui.TextInput(
                label=game[:45],
                placeholder="Ранг/уровень (можно пропустить)",
                required=False,
                max_length=100,
            )
            if draft.ranks.get(game):
                item.default = draft.ranks[game]
            self.rank_inputs[game] = item
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.draft.ranks = {
            game: (field.value.strip() or None)
            for game, field in self.rank_inputs.items()
        }
        if "AION 2" in self.draft.ranks:
            await send_temporary(
                interaction,
                "Для AION 2 выберите фракцию и укажите сервер:",
                view=AionProfileDetailsView(interaction.user.id, self.draft),
                ephemeral=True,
            )
            return
        await send_profile_preview(interaction, self.draft)


async def send_profile_preview(
    interaction: discord.Interaction, draft: ProfileDraft, *, edit: bool = False
) -> None:
    games_text = "\n".join(
        f"• {game}"
        + (f" — {rank}" if rank else "")
        + (
            f"\n  Сервер: {draft.game_details[game].get('server')}; "
            f"фракция: {draft.game_details[game].get('faction')}"
            if game in draft.game_details and draft.game_details[game].get("server")
            else ""
        )
        for game, rank in draft.ranks.items()
    )
    embed = discord.Embed(title="Проверьте анкету", color=0x5865F2)
    embed.add_field(name="Никнейм", value=draft.nickname)
    embed.add_field(name="Возраст", value=str(draft.age or "Не указан"))
    embed.add_field(name="Пол", value=draft.gender or "Не указан")
    embed.add_field(name="Игры", value=games_text or "—", inline=False)
    embed.add_field(name="О себе", value=draft.about, inline=False)
    embed.add_field(name="Цели", value=", ".join(draft.goals) or "—", inline=False)
    embed.add_field(
        name="Удобное время",
        value=", ".join(draft.convenient_time) or "—",
        inline=False,
    )
    kwargs = {
        "content": "Все верно?",
        "embed": embed,
        "view": ProfileConfirmView(interaction.user.id, draft),
    }
    if edit:
        await edit_temporary(interaction, **kwargs)
    else:
        await send_temporary(interaction, **kwargs, ephemeral=True)


class AionProfileFactionSelect(discord.ui.Select):
    def __init__(self, selected: str | None = None):
        super().__init__(
            placeholder="Фракция AION 2",
            options=[
                discord.SelectOption(
                    label=value, value=value, default=value == selected
                )
                for value in AION_2_FACTIONS
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.faction = self.values[0]
        await interaction.response.defer()


class AionProfileDetailsView(OwnedView):
    def __init__(self, owner_id: int, draft: ProfileDraft):
        super().__init__(owner_id)
        self.draft = draft
        current = draft.game_details.get("AION 2", {})
        self.faction = current.get("faction")
        self.add_item(AionProfileFactionSelect(self.faction))

    @discord.ui.button(label="Указать сервер", style=discord.ButtonStyle.success)
    async def server(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if not self.faction:
            await send_temporary(
                interaction, "Сначала выберите фракцию.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            AionProfileServerModal(self.draft, self.faction)
        )


class AionProfileServerModal(TemporaryModal, title="AION 2"):
    server = discord.ui.TextInput(label="Сервер", min_length=1, max_length=100)

    def __init__(self, draft: ProfileDraft, faction: str):
        super().__init__()
        self.draft = draft
        self.faction = faction
        current = draft.game_details.get("AION 2", {}).get("server")
        if current:
            self.server.default = current

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.draft.game_details["AION 2"] = {
            "server": self.server.value.strip(),
            "faction": self.faction,
        }
        await send_profile_preview(interaction, self.draft)


class ProfileConfirmView(OwnedView):
    def __init__(self, owner_id: int, draft: ProfileDraft):
        super().__init__(owner_id)
        self.draft = draft

    @discord.ui.button(label="Все верно", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        profile = await platform_repository.save_profile(
            platform="discord",
            user_id=interaction.user.id,
            nickname=self.draft.nickname,
            age=self.draft.age,
            gender=self.draft.gender,
            games=self.draft.ranks,
            game_details=self.draft.game_details,
            about=self.draft.about,
            goals=self.draft.goals,
            convenient_time=self.draft.convenient_time,
            contact_tag=str(interaction.user),
            is_active=self.draft.is_active,
        )
        asyncio.create_task(
            discord_statistics.record(
                interaction.user.id, str(interaction.user), "filled_profile"
            )
        )
        await edit_temporary(
            interaction,
            content="Анкета сохранена и доступна в поиске."
            if profile.is_active
            else "Анкета сохранена и остаётся скрытой из поиска.",
            embed=profile_embed(profile),
            view=MyProfileView(interaction.user.id, profile),
        )

    @discord.ui.button(
        label="Исправить", emoji="✏️", style=discord.ButtonStyle.secondary
    )
    async def edit(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ProfileBasicsModal(interaction.user.id, draft=self.draft)
        )

    @discord.ui.button(label="Игры и параметры", style=discord.ButtonStyle.secondary)
    async def options(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Измените нужные параметры. Остальные значения сохранены.",
            embed=None,
            view=ProfileOptionsView(self.owner_id, self.draft),
        )


class ProfileVisibilityView(OwnedView):
    @discord.ui.button(label="Да", style=discord.ButtonStyle.success)
    async def enable(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await platform_repository.set_profile_active(
            "discord", interaction.user.id, True
        )
        await edit_temporary(
            interaction,
            content=(
                "Анкета создана и доступна в общей выдаче Telegram и Discord. "
                "Фото можно добавить командой `/photo`."
            ),
            view=None,
        )

    @discord.ui.button(label="Нет", style=discord.ButtonStyle.secondary)
    async def disable(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await platform_repository.set_profile_active(
            "discord", interaction.user.id, False
        )
        await edit_temporary(
            interaction,
            content="Анкета сохранена, но скрыта из поиска. Вернуть её можно командой `/pause`.",
            view=None,
        )


class ProfileDeleteConfirmView(OwnedView):
    @discord.ui.button(label="Да, удалить", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await platform_repository.delete_profile("discord", interaction.user.id)
        await edit_temporary(interaction, content="Анкета удалена.", view=None)

    @discord.ui.button(label="Нет", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(interaction, content="Удаление отменено.", view=None)


class PublicPanelView(discord.ui.LayoutView):
    """Persistent Components V2 entry point posted in a public channel."""

    CUSTOM_ID = "teamseek:panel:open"
    CUSTOM_IDS = {
        "open": CUSTOM_ID,
        "search": "teamseek:panel:search",
        "profile": "teamseek:panel:profile",
        "clans": "teamseek:panel:clans",
        "website": "teamseek:panel:website",
    }

    def __init__(self):
        super().__init__(timeout=None)
        search_button = discord.ui.Button(
            label="Начать поиск",
            emoji="🎯",
            style=discord.ButtonStyle.primary,
            custom_id=self.CUSTOM_IDS["search"],
        )
        profile_button = discord.ui.Button(
            label="Моя анкета",
            emoji="👤",
            style=discord.ButtonStyle.secondary,
            custom_id=self.CUSTOM_IDS["profile"],
        )
        clans_button = discord.ui.Button(
            label="Кланы",
            emoji="🛡️",
            style=discord.ButtonStyle.secondary,
            custom_id=self.CUSTOM_IDS["clans"],
        )
        website_button = discord.ui.Button(
            label="Сайт GG.Store",
            emoji="🌐",
            style=discord.ButtonStyle.secondary,
            custom_id=self.CUSTOM_IDS["website"],
        )
        search_button.callback = self.open_search
        profile_button.callback = self.open_profile
        clans_button.callback = self.open_clans
        website_button.callback = self.open_website

        container = discord.ui.Container(accent_color=discord.Color.blurple())
        container.add_item(
            discord.ui.TextDisplay(
                "## 🔎 TeamSeek — поиск тиммейтов\n"
                "Создай анкету, найди игроков по любимой игре или подбери клан. "
                "Анкеты доступны в общей выдаче Discord и Telegram."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Нажми нужную кнопку — управление откроется **только для тебя** "
                "в приватном окне."
            )
        )
        container.add_item(discord.ui.ActionRow(search_button, profile_button))
        container.add_item(discord.ui.ActionRow(clans_button, website_button))
        self.add_item(container)

    async def _profile(self, interaction: discord.Interaction):
        if (
            settings.PRIMARY_GUILD_ID
            and interaction.guild_id != settings.PRIMARY_GUILD_ID
        ):
            await send_temporary(
                interaction,
                "TeamSeek доступен на основном сервере GG.Store.",
                ephemeral=True,
            )
            return None, False
        profile = await platform_repository.get_profile("discord", interaction.user.id)
        return profile, True

    async def open_teamseek(self, interaction: discord.Interaction) -> None:
        profile, allowed = await self._profile(interaction)
        if not allowed:
            return
        await send_temporary(
            interaction,
            "Меню TeamSeek",
            view=MenuView(interaction.user.id, has_profile=profile is not None),
            ephemeral=True,
        )

    async def open_search(self, interaction: discord.Interaction) -> None:
        profile, allowed = await self._profile(interaction)
        if not allowed:
            return
        if not profile:
            await send_temporary(
                interaction,
                "Для поиска сначала создайте анкету.",
                view=MenuView(interaction.user.id, has_profile=False),
                ephemeral=True,
            )
            return
        await send_temporary(
            interaction,
            "Как будем искать тиммейтов?",
            view=SearchModeView(interaction.user.id),
            ephemeral=True,
        )

    async def open_profile(self, interaction: discord.Interaction) -> None:
        profile, allowed = await self._profile(interaction)
        if not allowed:
            return
        if not profile:
            await send_temporary(
                interaction,
                "Анкета ещё не создана. Заполните её, чтобы начать поиск.",
                view=MenuView(interaction.user.id, has_profile=False),
                ephemeral=True,
            )
            return
        embed = profile_embed(profile)
        photo_path = await resolve_profile_photo(profile.photo, profile.photo_origin)
        kwargs = {
            "content": "Моя анкета",
            "embed": embed,
            "view": MyProfileView(interaction.user.id, profile),
            "ephemeral": True,
        }
        if photo_path:
            file = discord.File(photo_path, filename=photo_path.name)
            embed.set_image(url=f"attachment://{photo_path.name}")
            kwargs["file"] = file
        await send_temporary(interaction, **kwargs)

    async def open_clans(self, interaction: discord.Interaction) -> None:
        profile, allowed = await self._profile(interaction)
        if not allowed:
            return
        if not profile:
            await send_temporary(
                interaction, "Сначала создайте анкету игрока.", ephemeral=True
            )
            return
        await send_temporary(
            interaction,
            "Раздел кланов",
            view=ClanHubView(interaction.user.id),
            ephemeral=True,
        )

    async def open_website(self, interaction: discord.Interaction) -> None:
        _, allowed = await self._profile(interaction)
        if not allowed:
            return
        asyncio.create_task(
            discord_statistics.record(
                interaction.user.id, str(interaction.user), "website"
            )
        )
        await send_temporary(
            interaction, f"Перейти на сайт: {settings.WEBSITE_URL}", ephemeral=True
        )


class LegacyPublicPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Открыть TeamSeek", custom_id=PublicPanelView.CUSTOM_ID)
    async def open_teamseek(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await PublicPanelView().open_teamseek(interaction)


class MenuView(OwnedView):
    def __init__(self, owner_id: int, *, has_profile: bool):
        super().__init__(owner_id)
        self.has_profile = has_profile
        if has_profile:
            self.remove_item(self.form)
        else:
            for item in (self.search, self.profile, self.clans):
                self.remove_item(item)

    @discord.ui.button(
        label="Создать анкету", emoji="📝", style=discord.ButtonStyle.primary
    )
    async def form(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(ProfileBasicsModal(interaction.user.id))

    @discord.ui.button(
        label="Начать поиск", emoji="🔍", style=discord.ButtonStyle.success
    )
    async def search(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if not await platform_repository.get_profile("discord", interaction.user.id):
            await send_temporary(
                interaction, "Сначала создайте анкету через `/form`.", ephemeral=True
            )
            return
        await edit_temporary(
            interaction,
            content="Как будем искать тиммейтов?",
            view=SearchModeView(interaction.user.id),
        )

    @discord.ui.button(
        label="Моя анкета", emoji="👤", style=discord.ButtonStyle.secondary
    )
    async def profile(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        profile = await platform_repository.get_profile("discord", interaction.user.id)
        if not profile:
            await send_temporary(interaction, "Анкета ещё не создана.", ephemeral=True)
            return
        embed = profile_embed(profile)
        photo_path = await resolve_profile_photo(profile.photo, profile.photo_origin)
        kwargs = {
            "content": "Моя анкета",
            "embed": embed,
            "view": MyProfileView(interaction.user.id, profile),
            "attachments": [],
        }
        if photo_path:
            file = discord.File(photo_path, filename=photo_path.name)
            embed.set_image(url=f"attachment://{photo_path.name}")
            kwargs["attachments"] = [file]
        await edit_temporary(interaction, **kwargs)

    @discord.ui.button(label="Кланы", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def clans(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction, content="Раздел кланов", view=ClanHubView(interaction.user.id)
        )

    @discord.ui.button(
        label="Сайт GG.Store", emoji="🌐", style=discord.ButtonStyle.secondary
    )
    async def website(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        asyncio.create_task(
            discord_statistics.record(
                interaction.user.id, str(interaction.user), "website"
            )
        )
        await send_temporary(
            interaction, f"Перейти на сайт: {settings.WEBSITE_URL}", ephemeral=True
        )


class MyProfileView(OwnedView):
    def __init__(self, owner_id: int, profile):
        super().__init__(owner_id)
        self.profile = profile

    @discord.ui.button(
        label="Изменить анкету", emoji="✏️", style=discord.ButtonStyle.primary
    )
    async def edit(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ProfileBasicsModal(interaction.user.id, self.profile)
        )

    @discord.ui.button(label="Игры и параметры", style=discord.ButtonStyle.secondary)
    async def options(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Измените нужные параметры. Остальные значения сохранены.",
            embed=None,
            attachments=[],
            view=ProfileOptionsView(
                self.owner_id, ProfileDraft.from_profile(self.profile)
            ),
        )

    @discord.ui.button(label="В меню", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Меню TeamSeek",
            embed=None,
            attachments=[],
            view=MenuView(self.owner_id, has_profile=True),
        )


class SearchModeView(OwnedView):
    @discord.ui.button(
        label="По критериям", emoji="🎯", style=discord.ButtonStyle.primary
    )
    async def filtered(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Выберите игру:",
            view=GameSearchView(interaction.user.id, filtered=True),
        )

    @discord.ui.button(
        label="Все анкеты", emoji="📋", style=discord.ButtonStyle.secondary
    )
    async def all_profiles(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Выберите игру:",
            view=GameSearchView(interaction.user.id, filtered=False),
        )

    @discord.ui.button(label="В меню", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Меню TeamSeek",
            view=MenuView(self.owner_id, has_profile=True),
        )


class GameSearchSelect(discord.ui.Select):
    def __init__(self, filtered: bool):
        self.filtered = filtered
        super().__init__(
            placeholder="Игра",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=name, value=name) for name in GAME_LIST
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        game = self.values[0]
        asyncio.create_task(
            discord_statistics.record(
                interaction.user.id, str(interaction.user), "start_search"
            )
        )
        if self.filtered:
            await edit_temporary(
                interaction,
                content=f"Настройте поиск по **{game}**:",
                view=SearchCriteriaView(interaction.user.id, game),
            )
            return
        profiles = await platform_repository.search_profiles(
            viewer_platform="discord", viewer_user_id=interaction.user.id, game=game
        )
        if not profiles:
            await edit_temporary(
                interaction,
                content=f"По игре **{game}** пока нет активных анкет.",
                view=GameSearchView(interaction.user.id, filtered=False),
            )
            return
        await show_profile_list(
            interaction,
            profiles,
            game,
            filtered=False,
            edit=True,
        )


class GameSearchView(OwnedView):
    def __init__(self, owner_id: int, filtered: bool = True):
        super().__init__(owner_id)
        self.add_item(GameSearchSelect(filtered))

    @discord.ui.button(label="Назад", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Как будем искать тиммейтов?",
            view=SearchModeView(self.owner_id),
        )

    @discord.ui.button(label="В меню", style=discord.ButtonStyle.secondary)
    async def menu(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Меню TeamSeek",
            view=MenuView(self.owner_id, has_profile=True),
        )


class GoalSearchSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Цель поиска (необязательно)",
            options=[discord.SelectOption(label="Любая цель", value="any")]
            + [discord.SelectOption(label=value, value=value) for value in GOALS_LIST],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.goal = None if self.values[0] == "any" else self.values[0]
        await interaction.response.defer()


class AionSearchFactionSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Фракция AION 2 (необязательно)",
            options=[discord.SelectOption(label="Любая фракция", value="any")]
            + [
                discord.SelectOption(label=value, value=value)
                for value in AION_2_FACTIONS
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.faction = None if self.values[0] == "any" else self.values[0]
        await interaction.response.defer()


class SearchCriteriaView(OwnedView):
    def __init__(self, owner_id: int, game: str):
        super().__init__(owner_id)
        self.game = game
        self.goal: str | None = None
        self.faction: str | None = None
        self.add_item(GoalSearchSelect())
        if game == "AION 2":
            self.add_item(AionSearchFactionSelect())

    @discord.ui.button(label="Указать ранг и найти", style=discord.ButtonStyle.success)
    async def find(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            SearchRankModal(self.game, self.goal, self.faction)
        )

    @discord.ui.button(label="Назад", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Выберите игру:",
            view=GameSearchView(self.owner_id, filtered=True),
        )


class SearchRankModal(TemporaryModal, title="Критерии поиска"):
    rank = discord.ui.TextInput(
        label="Ранг/уровень (необязательно)", required=False, max_length=100
    )
    server = discord.ui.TextInput(
        label="Сервер AION 2 (необязательно)", required=False, max_length=100
    )

    def __init__(self, game: str, goal: str | None, faction: str | None):
        super().__init__()
        self.game = game
        self.goal = goal
        self.faction = faction
        if game != "AION 2":
            self.remove_item(self.server)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        profiles = await platform_repository.search_profiles(
            viewer_platform="discord",
            viewer_user_id=interaction.user.id,
            game=self.game,
            rank=self.rank.value.strip() or None,
            goal=self.goal,
            server=self.server.value.strip() or None if self.game == "AION 2" else None,
            faction=self.faction if self.game == "AION 2" else None,
        )
        if not profiles:
            await send_temporary(
                interaction,
                "По выбранным критериям пока нет активных анкет. Попробуйте `/all`.",
                ephemeral=True,
            )
            return
        await show_profile_list(
            interaction,
            profiles,
            self.game,
            filtered=True,
            edit=False,
        )


PROFILES_PER_PAGE = 5


def _profile_summary(profile, game: str) -> str:
    selected_game = next(
        (item for item in profile.games if item.name == game),
        None,
    )
    details = [platform_badge(profile.platform)]
    if profile.age:
        details.append(f"{profile.age} лет")
    details.append(f"уровень {(profile.experience or 0) // 100 + 1} ⚡")
    if selected_game and selected_game.rank:
        details.append(f"ранг: {selected_game.rank}")
    if selected_game and selected_game.server:
        details.append(f"сервер: {selected_game.server}")
    if selected_game and selected_game.faction:
        details.append(f"фракция: {selected_game.faction}")

    about = " ".join((profile.about or "О себе не указано").split())
    if len(about) > 160:
        about = f"{about[:157]}..."
    goals = ", ".join(profile.goals or [])
    goals_line = f"\n🎯 {goals}" if goals else ""
    return f"### {profile.nickname}\n{' · '.join(details)}\n{about}{goals_line}"


class ProfileActionsView(OwnedView):
    def __init__(self, owner_id: int, target_profile_id: int, game: str):
        super().__init__(owner_id)
        self.target_profile_id = target_profile_id
        self.game = game

    @discord.ui.button(label="Написать", emoji="✉️", style=discord.ButtonStyle.primary)
    async def message(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ContactMessageModal(self.target_profile_id, self.game)
        )

    @discord.ui.button(
        label="Пригласить", emoji="🎮", style=discord.ButtonStyle.success
    )
    async def invite(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await send_contact(
            interaction, self.target_profile_id, self.game, "invite", None
        )


async def send_profile_details(
    interaction: discord.Interaction, profile, game: str
) -> None:
    """Open a full profile without replacing the paginated catalogue."""

    await interaction.response.defer(ephemeral=True, thinking=True)
    current = await platform_repository.get_profile_by_id(profile.id)
    if not current or not current.is_active:
        await followup_temporary(
            interaction, "Анкета больше недоступна.", ephemeral=True
        )
        return
    asyncio.create_task(
        discord_statistics.record(
            interaction.user.id, str(interaction.user), "open_profile"
        )
    )
    embed = profile_embed(current, game)
    kwargs = {
        "embed": embed,
        "view": ProfileActionsView(interaction.user.id, current.id, game),
        "ephemeral": True,
    }
    photo_path = await resolve_profile_photo(current.photo, current.photo_origin)
    if photo_path:
        filename = f"profile-{current.id}{photo_path.suffix}"
        file = discord.File(photo_path, filename=filename)
        embed.set_image(url=file.uri)
        kwargs["file"] = file
    await followup_temporary(interaction, **kwargs)


class ProfileListView(OwnedLayoutView):
    """Components V2 catalogue with five compact player profiles per page."""

    def __init__(
        self,
        owner_id: int,
        profiles,
        game: str,
        *,
        filtered: bool,
        page: int = 0,
        photo_files: dict[int, discord.File] | None = None,
    ):
        super().__init__(owner_id)
        self.profiles = list(profiles)
        if not self.profiles:
            raise ValueError("ProfileListView requires at least one profile")
        self.game = game
        self.filtered = filtered
        self.page_count = max(
            1, (len(self.profiles) + PROFILES_PER_PAGE - 1) // PROFILES_PER_PAGE
        )
        self.page = max(0, min(page, self.page_count - 1))
        photo_files = photo_files or {}

        start = self.page * PROFILES_PER_PAGE
        page_profiles = self.profiles[start : start + PROFILES_PER_PAGE]
        container = discord.ui.Container(accent_color=discord.Color.blurple())
        container.add_item(
            discord.ui.TextDisplay(
                f"## 🎮 Анкеты по игре {game}\n"
                f"Найдено: **{len(self.profiles)}** · "
                f"страница **{self.page + 1} из {self.page_count}** · "
                "нажмите никнейм, чтобы открыть полную анкету."
            )
        )

        for profile in page_profiles:
            container.add_item(discord.ui.Separator())
            open_button = discord.ui.Button(
                label=profile.nickname[:80],
                emoji="👤",
                style=discord.ButtonStyle.primary,
            )

            async def open_profile(
                interaction: discord.Interaction, selected_profile=profile
            ) -> None:
                await send_profile_details(interaction, selected_profile, self.game)

            open_button.callback = open_profile
            photo_file = photo_files.get(profile.id)
            if photo_file:
                container.add_item(
                    discord.ui.Section(
                        _profile_summary(profile, game),
                        accessory=discord.ui.Thumbnail(
                            photo_file,
                            description=f"Фото игрока {profile.nickname}",
                        ),
                    )
                )
                container.add_item(discord.ui.ActionRow(open_button))
            else:
                container.add_item(
                    discord.ui.TextDisplay(_profile_summary(profile, game))
                )
                container.add_item(discord.ui.ActionRow(open_button))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        previous = discord.ui.Button(
            label="Назад",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            disabled=self.page == 0,
        )
        next_button = discord.ui.Button(
            label="Вперёд",
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= self.page_count - 1,
        )
        games = discord.ui.Button(
            label="К выбору игры",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
        )

        async def previous_page(interaction: discord.Interaction) -> None:
            await self._show_page(interaction, self.page - 1)

        async def next_page(interaction: discord.Interaction) -> None:
            await self._show_page(interaction, self.page + 1)

        async def back_to_games(interaction: discord.Interaction) -> None:
            await send_temporary(
                interaction,
                "Выберите игру:",
                view=GameSearchView(self.owner_id, filtered=self.filtered),
                ephemeral=True,
            )

        previous.callback = previous_page
        next_button.callback = next_page
        games.callback = back_to_games
        container.add_item(discord.ui.ActionRow(previous, next_button, games))
        self.add_item(container)

    async def _show_page(self, interaction: discord.Interaction, page: int) -> None:
        view, files = await build_profile_list_view(
            self.owner_id,
            self.profiles,
            self.game,
            filtered=self.filtered,
            page=page,
        )
        await edit_temporary(interaction, attachments=files, view=view)


async def build_profile_list_view(
    owner_id: int,
    profiles,
    game: str,
    *,
    filtered: bool,
    page: int = 0,
) -> tuple[ProfileListView, list[discord.File]]:
    """Build one profile catalogue page and attach only its visible photos."""

    profiles = list(profiles)
    page_count = max(1, (len(profiles) + PROFILES_PER_PAGE - 1) // PROFILES_PER_PAGE)
    page = max(0, min(page, page_count - 1))
    start = page * PROFILES_PER_PAGE
    photo_files: dict[int, discord.File] = {}
    files: list[discord.File] = []
    for profile in profiles[start : start + PROFILES_PER_PAGE]:
        try:
            photo_path = await resolve_profile_photo(
                profile.photo, profile.photo_origin
            )
            if not photo_path:
                continue
            filename = f"profile-{profile.id}{photo_path.suffix}"
            file = discord.File(photo_path, filename=filename)
        except (OSError, aiohttp.ClientError):
            logging.getLogger(__name__).warning(
                "Photo unavailable for profile %s", profile.id
            )
            continue
        photo_files[profile.id] = file
        files.append(file)
    return (
        ProfileListView(
            owner_id,
            profiles,
            game,
            filtered=filtered,
            page=page,
            photo_files=photo_files,
        ),
        files,
    )


async def show_profile_list(
    interaction: discord.Interaction,
    profiles,
    game: str,
    *,
    filtered: bool,
    edit: bool,
) -> None:
    view, files = await build_profile_list_view(
        interaction.user.id, profiles, game, filtered=filtered
    )
    if edit:
        await edit_temporary(
            interaction,
            content=None,
            embed=None,
            attachments=files,
            view=view,
        )
        return
    await send_temporary(
        interaction,
        view=view,
        files=files,
        ephemeral=True,
    )


class ContactMessageModal(TemporaryModal, title="Сообщение игроку"):
    message = discord.ui.TextInput(
        label="Текст", style=discord.TextStyle.paragraph, min_length=1, max_length=1500
    )

    def __init__(self, target_profile_id: int, game: str):
        super().__init__()
        self.target_profile_id = target_profile_id
        self.game = game

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await send_contact(
            interaction,
            self.target_profile_id,
            self.game,
            "message",
            self.message.value.strip(),
        )


async def send_contact(
    interaction: discord.Interaction,
    target_profile_id: int,
    game: str,
    kind: str,
    message: str | None,
) -> None:
    sender = await platform_repository.get_profile("discord", interaction.user.id)
    target = await platform_repository.get_profile_by_id(target_profile_id)
    if not sender or not target:
        await send_temporary(
            interaction, "Одна из анкет больше недоступна.", ephemeral=True
        )
        return
    request = await platform_repository.create_contact_request(
        sender_profile_id=sender.id,
        target_profile_id=target.id,
        kind=kind,
        game=game,
        message=message,
    )
    heading = "🎮 Приглашение в игру" if kind == "invite" else "✉️ Новое сообщение"
    body = (
        f"{heading}\nОт: {sender.nickname} ({platform_badge(sender.platform)})\n"
        f"Игра: {game}\n"
    )
    if message:
        body += f"\n{message}\n"
    body += f"\nОтветить: `{reply_instruction(target, request.id)}`"
    result = await deliver_text(target, body)
    if result.delivered:
        if kind == "message":
            await platform_repository.award_first_message(sender.id)
        await send_temporary(
            interaction,
            "Сообщение отправлено. Ответ придёт в личные сообщения.",
            ephemeral=True,
        )
        asyncio.create_task(
            discord_statistics.record(
                interaction.user.id, str(interaction.user), "invite_game"
            )
        )
    else:
        await platform_repository.mark_contact_failed(request.id)
        await send_temporary(
            interaction,
            "Не удалось доставить сообщение: у пользователя могут быть закрыты личные сообщения. "
            "Попробуйте другую анкету.",
            ephemeral=True,
        )


class RatingModal(TemporaryModal, title="Оценить тиммейта"):
    polite = discord.ui.TextInput(label="Вежливость (1–5)", min_length=1, max_length=1)
    skill = discord.ui.TextInput(label="Скилл (1–5)", min_length=1, max_length=1)
    teamwork = discord.ui.TextInput(
        label="Командная игра (1–5)", min_length=1, max_length=1
    )

    def __init__(self, request_id: int):
        super().__init__()
        self.request_id = request_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            values = tuple(
                int(field.value) for field in (self.polite, self.skill, self.teamwork)
            )
        except ValueError:
            await send_temporary(
                interaction,
                "Каждая оценка должна быть числом от 1 до 5.",
                ephemeral=True,
            )
            return
        request = await platform_repository.get_contact_request(self.request_id)
        reviewer = await platform_repository.get_profile("discord", interaction.user.id)
        if not request or not reviewer or request.sender_profile_id != reviewer.id:
            await send_temporary(
                interaction, "Это приглашение вам недоступно.", ephemeral=True
            )
            return
        try:
            is_new = await platform_repository.upsert_review(
                reviewer_profile_id=reviewer.id,
                target_profile_id=request.target_profile_id,
                contact_request_id=request.id,
                polite=values[0],
                skill=values[1],
                team_game=values[2],
            )
        except ValueError as exc:
            await send_temporary(interaction, str(exc), ephemeral=True)
            return
        xp_text = ""
        if is_new:
            (
                awarded,
                old_level,
                new_level,
            ) = await platform_repository.award_rating_experience(
                reviewer.id, request.target_profile_id
            )
            if awarded:
                xp_text = " Начислено 10 опыта."
                if new_level > old_level:
                    xp_text += f" Новый уровень: {new_level} ⚡"
        await platform_repository.set_contact_status(request.id, "completed")
        await send_temporary(
            interaction,
            "Спасибо! Оценка сохранена. Её можно изменить той же командой." + xp_text,
            ephemeral=True,
        )


class RatingPromptView(OwnedView):
    """Persistent 24-hour result prompt required by the product flow."""

    def __init__(self, owner_id: int, request_id: int, *, in_process: bool = False):
        super().__init__(owner_id, timeout=None)
        self.request_id = request_id
        yes = discord.ui.Button(
            label="Да",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"teamseek:rating:{request_id}:yes",
        )
        waiting = discord.ui.Button(
            label="В процессе",
            emoji="⌛",
            style=discord.ButtonStyle.primary,
            custom_id=f"teamseek:rating:{request_id}:waiting",
            disabled=in_process,
        )
        no = discord.ui.Button(
            label="Нет",
            emoji="❌",
            style=discord.ButtonStyle.secondary,
            custom_id=f"teamseek:rating:{request_id}:no",
        )
        yes.callback = self.yes
        waiting.callback = self.waiting
        no.callback = self.no
        self.add_item(yes)
        self.add_item(waiting)
        self.add_item(no)

    async def yes(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RatingModal(self.request_id))

    async def waiting(self, interaction: discord.Interaction) -> None:
        await platform_repository.set_contact_status(self.request_id, "in_process")
        await edit_temporary(
            interaction,
            content="Хорошо, вернёмся к вопросу позже. Оценить игрока можно командой `/rate`.",
            view=RatingPromptView(self.owner_id, self.request_id, in_process=True),
        )

    async def no(self, interaction: discord.Interaction) -> None:
        await platform_repository.set_contact_status(self.request_id, "declined")
        await edit_temporary(
            interaction, content="Понял. Оценка не требуется.", view=None
        )


class ClanHubView(OwnedView):
    @discord.ui.button(
        label="Создать клан", emoji="➕", style=discord.ButtonStyle.success
    )
    async def create(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Выберите игру и, для AION 2, фракцию:",
            view=ClanSetupView(interaction.user.id),
        )

    @discord.ui.button(label="Мои кланы", style=discord.ButtonStyle.secondary)
    async def own(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clans = await platform_repository.own_clans("discord", interaction.user.id)
        if not clans:
            await send_temporary(
                interaction, "У вас пока нет анкет кланов.", ephemeral=True
            )
            return
        view, files = await build_clan_list_view(interaction.user.id, clans, own=True)
        await edit_temporary(
            interaction,
            content=None,
            embed=None,
            attachments=files,
            view=view,
        )

    @discord.ui.button(
        label="Найти клан", emoji="🔍", style=discord.ButtonStyle.primary
    )
    async def search(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Выберите игру:",
            view=ClanSearchView(interaction.user.id),
        )

    @discord.ui.button(label="В меню", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content="Меню TeamSeek",
            view=MenuView(self.owner_id, has_profile=True),
        )


class ClanChoiceSelect(discord.ui.Select):
    def __init__(self, field_name: str, placeholder: str, values: list[str]):
        super().__init__(
            placeholder=placeholder,
            options=[
                discord.SelectOption(label=value, value=value) for value in values
            ],
        )
        self.field_name = field_name

    async def callback(self, interaction: discord.Interaction) -> None:
        setattr(self.view, self.field_name, self.values[0])
        for option in self.options:
            option.default = option.value == self.values[0]
        if self.field_name == "game" and isinstance(self.view, ClanSetupView):
            for item in list(self.view.children):
                if isinstance(item, ClanChoiceSelect) and item.field_name == "faction":
                    self.view.remove_item(item)
            self.view.faction = None
            if self.values[0] == "AION 2":
                self.view.add_item(
                    ClanChoiceSelect(
                        "faction", "Фракция AION 2 (обязательно)", AION_2_FACTIONS
                    )
                )
            await edit_temporary(interaction, view=self.view)
        else:
            await interaction.response.defer()


class ClanSetupView(OwnedView):
    def __init__(self, owner_id: int):
        super().__init__(owner_id)
        self.game: str | None = None
        self.faction: str | None = None
        self.add_item(ClanChoiceSelect("game", "Игра", list(GAME_LIST)))

    @discord.ui.button(label="Продолжить", style=discord.ButtonStyle.success)
    async def continue_form(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if not self.game:
            await send_temporary(interaction, "Сначала выберите игру.", ephemeral=True)
            return
        if self.game == "AION 2" and not self.faction:
            await send_temporary(
                interaction, "Для AION 2 выберите фракцию.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ClanModal(self.game, self.faction))

    @discord.ui.button(label="Назад", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction, content="Раздел кланов", view=ClanHubView(self.owner_id)
        )


class RetryClanView(OwnedView):
    def __init__(self, owner_id: int, draft):
        super().__init__(owner_id)
        self.draft = draft

    @discord.ui.button(label="Исправить данные", style=discord.ButtonStyle.primary)
    async def retry(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ClanModal(self.draft["game"], self.draft["faction"], draft=self.draft)
        )


class ClanModal(TemporaryModal, title="Анкета клана"):
    name = discord.ui.TextInput(label="Название", min_length=1, max_length=100)
    description = discord.ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1500,
    )
    demands = discord.ui.TextInput(
        label="Требования",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
    )
    server = discord.ui.TextInput(
        label="Сервер (для MMO)", required=False, max_length=100
    )
    faction_input = discord.ui.TextInput(
        label="Фракция (для MMO)", required=False, max_length=100
    )

    def __init__(self, game: str, faction: str | None, draft=None):
        super().__init__()
        self.game = game
        self.faction = faction
        if game not in MMO_GAMES:
            self.remove_item(self.server)
            self.remove_item(self.faction_input)
        else:
            self.server.required = True
            self.server.label = "Сервер (обязательно)"
            if game == "AION 2" and faction:
                self.remove_item(self.faction_input)
            else:
                self.faction_input.required = True
                self.faction_input.label = "Фракция (обязательно)"
        if draft:
            for name in ("name", "description", "demands", "server"):
                getattr(self, name).default = draft.get(name) or ""
        if faction:
            self.faction_input.default = faction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        server = self.server.value.strip() or None
        faction = self.faction_input.value.strip() or self.faction
        draft = {
            "name": self.name.value.strip(),
            "game": self.game,
            "description": self.description.value.strip(),
            "demands": self.demands.value.strip(),
            "server": server if self.game in MMO_GAMES else None,
            "faction": faction if self.game in MMO_GAMES else None,
        }
        if self.game in MMO_GAMES and (not server or not faction):
            await send_temporary(
                interaction,
                "Для этой MMO обязательно укажите сервер и фракцию.",
                view=RetryClanView(interaction.user.id, draft),
                ephemeral=True,
            )
            return
        if self.game == "AION 2" and faction not in AION_2_FACTIONS:
            await send_temporary(
                interaction,
                "Для AION 2 выберите фракцию: Элийцы или Асмодиане.",
                view=RetryClanView(interaction.user.id, draft),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=draft["name"],
            description=draft["description"],
            color=discord.Color.dark_teal(),
        )
        embed.add_field(name="Игра", value=draft["game"])
        if draft["server"]:
            embed.add_field(name="Сервер", value=draft["server"])
        if draft["faction"]:
            embed.add_field(name="Фракция", value=draft["faction"])
        embed.add_field(name="Требования", value=draft["demands"], inline=False)
        await send_temporary(
            interaction,
            "Все верно?",
            embed=embed,
            view=ClanConfirmView(interaction.user.id, draft),
            ephemeral=True,
        )


class ClanConfirmView(OwnedView):
    def __init__(self, owner_id: int, draft: dict[str, str | None]):
        super().__init__(owner_id)
        self.draft = draft
        self._save_lock = asyncio.Lock()
        self._created_clan = None

    @discord.ui.button(label="Все верно", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self._save_lock:
            if self._created_clan is None:
                try:
                    self._created_clan = await platform_repository.create_clan(
                        platform="discord", user_id=interaction.user.id, **self.draft
                    )
                except (SQLAlchemyError, OSError, TimeoutError) as exc:
                    logging.getLogger(__name__).error(
                        "Clan creation failed (%s)", type(exc).__name__
                    )
                    await followup_temporary(
                        interaction,
                        "Не удалось подтвердить сохранение клана. Данные формы сохранены. "
                        "Проверьте «Мои кланы» перед повторной попыткой.",
                        ephemeral=True,
                    )
                    return
            clan = self._created_clan
        await followup_temporary(
            interaction,
            content=(
                f"Анкета клана создана. Нажмите «Аватар», чтобы добавить изображение. "
                f"Также доступна команда /clan_photo clan_id:{clan.id}."
            ),
            embed=clan_embed(clan),
            view=OwnClanActionsView(interaction.user.id, clan),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Исправить", emoji="✏️", style=discord.ButtonStyle.secondary
    )
    async def edit(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ClanModal(str(self.draft["game"]), self.draft["faction"], draft=self.draft)
        )


class ClanResultSelect(discord.ui.Select):
    def __init__(self, clans):
        super().__init__(
            placeholder="Открыть клан",
            options=[
                discord.SelectOption(
                    label=clan.name[:100],
                    value=str(clan.id),
                    description=f"{clan.game} • {platform_badge(clan.platform)}"[:100],
                )
                for clan in clans[:25]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        clan = next(
            (item for item in self.view.clans if item.id == int(self.values[0])), None
        )
        if not clan:
            await send_temporary(
                interaction, "Анкета клана не найдена.", ephemeral=True
            )
            return
        await send_clan_details(interaction, clan)


async def send_clan_details(interaction: discord.Interaction, clan) -> None:
    """Open one full clan card without replacing the paginated clan catalogue."""

    own_clan = clan.platform == "discord" and clan.user_id == interaction.user.id
    embed = clan_embed(clan)
    photo_path = await resolve_profile_photo(clan.photo, clan.photo_origin)
    kwargs = {
        "embed": embed,
        "view": (
            OwnClanActionsView(interaction.user.id, clan)
            if own_clan
            else ClanActionsView(interaction.user.id, clan.id)
        ),
        "ephemeral": True,
    }
    if photo_path:
        filename = f"clan-{clan.id}{photo_path.suffix}"
        file = discord.File(photo_path, filename=filename)
        embed.set_image(url=file.uri)
        kwargs["file"] = file
    await send_temporary(interaction, **kwargs)


async def save_clan_avatar(
    interaction, clan_id: int, upload: discord.Attachment
) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    clan = await platform_repository.get_clan_by_id(clan_id)
    if not clan or clan.platform != "discord" or clan.user_id != interaction.user.id:
        await followup_temporary(
            interaction, "Ваша анкета клана не найдена.", ephemeral=True
        )
        return
    if upload.content_type not in ALLOWED_IMAGE_TYPES or upload.size > MAX_IMAGE_BYTES:
        await followup_temporary(
            interaction, "Прикрепите JPG, PNG, WEBP или GIF до 10 МБ.", ephemeral=True
        )
        return
    try:
        reference = await store_image(
            await upload.read(), upload.content_type, upload.filename
        )
        updated = await platform_repository.update_clan_photo(
            clan_id, "discord", interaction.user.id, reference, "local"
        )
    except (ValueError, discord.HTTPException, OSError):
        await followup_temporary(
            interaction,
            "Не удалось сохранить изображение. Попробуйте загрузить файл ещё раз.",
            ephemeral=True,
        )
        return
    await followup_temporary(
        interaction,
        "Аватар клана обновлён." if updated else "Клан больше недоступен.",
        ephemeral=True,
    )


class ClanAvatarModal(TemporaryModal, title="Аватар клана"):
    def __init__(self, clan_id: int):
        super().__init__()
        self.clan_id = clan_id
        self.upload = discord.ui.FileUpload(min_values=1, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="Изображение",
                description="JPG, PNG, WEBP или GIF до 10 МБ",
                component=self.upload,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await save_clan_avatar(interaction, self.clan_id, self.upload.values[0])


class OwnClanActionsView(OwnedView):
    def __init__(self, owner_id: int, clan):
        super().__init__(owner_id)
        self.clan = clan

    @discord.ui.button(label="Аватар", emoji="🖼️", style=discord.ButtonStyle.secondary)
    async def avatar(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(ClanAvatarModal(self.clan.id))

    @discord.ui.button(label="Изменить", emoji="✏️", style=discord.ButtonStyle.primary)
    async def edit(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(ClanEditModal(self.clan))

    @discord.ui.button(
        label="Сменить игру", emoji="🎮", style=discord.ButtonStyle.secondary
    )
    async def game(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await send_temporary(
            interaction,
            "Выберите новую игру:",
            view=ClanGameEditView(interaction.user.id, self.clan),
            ephemeral=True,
        )

    @discord.ui.button(label="Удалить", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction,
            content=f"Удалить анкету клана **{self.clan.name}**?",
            view=ClanDeleteConfirmView(interaction.user.id, self.clan.id),
        )

    @discord.ui.button(
        label="Назад к кланам", emoji="↩️", style=discord.ButtonStyle.secondary
    )
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        clans = await platform_repository.own_clans("discord", interaction.user.id)
        if clans:
            view, files = await build_clan_list_view(
                interaction.user.id, clans, own=True
            )
        else:
            view, files = ClanHubView(interaction.user.id), []
        await edit_temporary(
            interaction,
            content=None if clans else "Раздел кланов",
            embed=None,
            attachments=files,
            view=view,
        )


class ClanEditModal(TemporaryModal, title="Изменить клан"):
    name = discord.ui.TextInput(label="Название", min_length=1, max_length=100)
    description = discord.ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1500,
    )
    demands = discord.ui.TextInput(
        label="Требования",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
    )
    server = discord.ui.TextInput(
        label="Сервер (для MMO)", required=False, max_length=100
    )
    faction = discord.ui.TextInput(
        label="Фракция (для MMO)", required=False, max_length=100
    )

    def __init__(self, clan):
        super().__init__()
        self.clan = clan
        self.name.default = clan.name
        self.description.default = clan.description
        self.demands.default = clan.demands
        self.server.default = clan.server or ""
        self.faction.default = clan.faction or ""
        if clan.game not in MMO_GAMES:
            self.remove_item(self.server)
            self.remove_item(self.faction)
        else:
            self.server.required = True
            self.server.label = "Сервер (обязательно)"
            self.faction.required = True
            self.faction.label = "Фракция (обязательно)"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        server = self.server.value.strip() or None
        faction = self.faction.value.strip() or None
        if self.clan.game in MMO_GAMES and (not server or not faction):
            await send_temporary(
                interaction,
                "Для этой MMO обязательны сервер и фракция.",
                ephemeral=True,
            )
            return
        if self.clan.game == "AION 2" and faction not in AION_2_FACTIONS:
            await send_temporary(
                interaction,
                "Для AION 2 фракция должна быть «Элийцы» или «Асмодиане».",
                ephemeral=True,
            )
            return
        clan = await platform_repository.update_clan(
            clan_id=self.clan.id,
            platform="discord",
            user_id=interaction.user.id,
            name=self.name.value.strip(),
            game=self.clan.game,
            description=self.description.value.strip(),
            demands=self.demands.value.strip(),
            server=server,
            faction=faction,
        )
        await send_temporary(
            interaction,
            "Анкета клана обновлена.",
            embed=clan_embed(clan),
            ephemeral=True,
        )


class ClanGameEditSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Новая игра",
            options=[
                discord.SelectOption(label=name, value=name) for name in GAME_LIST
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        game = self.values[0]
        view = self.view
        if game in MMO_GAMES:
            await interaction.response.send_modal(ClanGameChangeModal(view.clan, game))
            return
        clan = await platform_repository.update_clan(
            clan_id=view.clan.id,
            platform="discord",
            user_id=interaction.user.id,
            name=view.clan.name,
            game=game,
            description=view.clan.description,
            demands=view.clan.demands,
            server=None,
            faction=None,
        )
        await edit_temporary(
            interaction,
            content="Игра клана обновлена.",
            embed=clan_embed(clan),
            view=None,
        )


class ClanGameEditView(OwnedView):
    def __init__(self, owner_id: int, clan):
        super().__init__(owner_id)
        self.clan = clan
        self.add_item(ClanGameEditSelect())


class ClanGameChangeModal(TemporaryModal, title="Новая MMO"):
    server = discord.ui.TextInput(label="Сервер", min_length=1, max_length=100)
    faction = discord.ui.TextInput(label="Фракция", min_length=1, max_length=100)

    def __init__(self, clan, game: str):
        super().__init__()
        self.clan = clan
        self.game = game

    async def on_submit(self, interaction: discord.Interaction) -> None:
        faction = self.faction.value.strip()
        if self.game == "AION 2" and faction not in AION_2_FACTIONS:
            await send_temporary(
                interaction,
                "Для AION 2 фракция должна быть «Элийцы» или «Асмодиане».",
                ephemeral=True,
            )
            return
        clan = await platform_repository.update_clan(
            clan_id=self.clan.id,
            platform="discord",
            user_id=interaction.user.id,
            name=self.clan.name,
            game=self.game,
            description=self.clan.description,
            demands=self.clan.demands,
            server=self.server.value.strip(),
            faction=faction,
        )
        await send_temporary(
            interaction, "Игра клана обновлена.", embed=clan_embed(clan), ephemeral=True
        )


class ClanDeleteConfirmView(OwnedView):
    def __init__(self, owner_id: int, clan_id: int):
        super().__init__(owner_id)
        self.clan_id = clan_id

    @discord.ui.button(label="Да, удалить", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        deleted = await platform_repository.delete_clan(
            self.clan_id, "discord", interaction.user.id
        )
        await edit_temporary(
            interaction,
            content="Анкета клана удалена." if deleted else "Анкета клана не найдена.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Нет", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        clan = await platform_repository.get_clan_by_id(self.clan_id)
        await edit_temporary(
            interaction,
            content="Удаление отменено.",
            embed=clan_embed(clan) if clan else None,
            view=OwnClanActionsView(self.owner_id, clan) if clan else None,
        )


class ClanActionsView(OwnedView):
    def __init__(self, owner_id: int, clan_id: int):
        super().__init__(owner_id)
        self.clan_id = clan_id

    @discord.ui.button(
        label="Отправить заявку", emoji="🏰", style=discord.ButtonStyle.success
    )
    async def apply(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(ClanApplicationModal(self.clan_id))


class ClanApplicationModal(TemporaryModal, title="Заявка в клан"):
    message = discord.ui.TextInput(
        label="Сообщение лидеру",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, clan_id: int):
        super().__init__()
        self.clan_id = clan_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        clan = await platform_repository.get_clan_by_id(self.clan_id)
        sender = await platform_repository.get_profile("discord", interaction.user.id)
        if not clan or not sender:
            await send_temporary(
                interaction, "Клан или ваша анкета больше недоступны.", ephemeral=True
            )
            return
        leader = await platform_repository.get_profile(clan.platform, clan.user_id)
        if not leader:
            await send_temporary(
                interaction, "Анкета лидера клана недоступна.", ephemeral=True
            )
            return
        request = await platform_repository.create_contact_request(
            sender_profile_id=sender.id,
            target_profile_id=leader.id,
            kind="clan_application",
            game=clan.game,
            message=self.message.value.strip() or None,
        )
        text = (
            f"🏰 Заявка в клан {clan.name}\n"
            f"Игрок: {sender.nickname} ({platform_badge(sender.platform)})\n"
            f"Игра: {clan.game}"
        )
        if self.message.value.strip():
            text += f"\n\n{self.message.value.strip()}"
        text += (
            f"\n\nПринять: `{accept_instruction(leader, request.id)}`"
            f"\nОтветить: `{reply_instruction(leader, request.id)}`"
        )
        result = await deliver_text(leader, text)
        if not result.delivered:
            await platform_repository.mark_contact_failed(request.id)
        await send_temporary(
            interaction,
            "Заявка отправлена."
            if result.delivered
            else "Не удалось доставить заявку лидеру.",
            ephemeral=True,
        )


CLANS_PER_PAGE = 5


def _clan_summary(clan) -> str:
    description = " ".join((clan.description or "Без описания").split())
    if len(description) > 180:
        description = f"{description[:177]}..."
    details = [f"🎮 **{clan.game}**", platform_badge(clan.platform)]
    if getattr(clan, "server", None):
        details.append(f"сервер: {clan.server}")
    if getattr(clan, "faction", None):
        details.append(f"фракция: {clan.faction}")
    return f"### {clan.name}\n{' · '.join(details)}\n{description}"


class ClanListView(OwnedLayoutView):
    """Components V2 catalogue with full clan previews and named buttons."""

    def __init__(
        self,
        owner_id: int,
        clans,
        *,
        own: bool = False,
        page: int = 0,
        photo_files: dict[int, discord.File] | None = None,
    ):
        super().__init__(owner_id)
        self.clans = list(clans)
        self.own = own
        self.page_count = max(
            1, (len(self.clans) + CLANS_PER_PAGE - 1) // CLANS_PER_PAGE
        )
        self.page = max(0, min(page, self.page_count - 1))
        photo_files = photo_files or {}

        start = self.page * CLANS_PER_PAGE
        page_clans = self.clans[start : start + CLANS_PER_PAGE]
        heading = "Ваши кланы" if own else "Найденные кланы"
        container = discord.ui.Container(accent_color=discord.Color.dark_teal())
        container.add_item(
            discord.ui.TextDisplay(
                f"## 🛡️ {heading}\n"
                f"Страница **{self.page + 1} из {self.page_count}** · "
                "нажмите название, чтобы открыть полную анкету."
            )
        )

        for clan in page_clans:
            container.add_item(discord.ui.Separator())
            open_button = discord.ui.Button(
                label=clan.name[:80],
                emoji="📜",
                style=discord.ButtonStyle.primary,
            )

            async def open_clan(
                interaction: discord.Interaction, selected_clan=clan
            ) -> None:
                await send_clan_details(interaction, selected_clan)

            open_button.callback = open_clan
            photo_file = photo_files.get(clan.id)
            if photo_file:
                container.add_item(
                    discord.ui.Section(
                        _clan_summary(clan),
                        accessory=discord.ui.Thumbnail(
                            photo_file, description=f"Эмблема клана {clan.name}"
                        ),
                    )
                )
                container.add_item(discord.ui.ActionRow(open_button))
            else:
                container.add_item(discord.ui.TextDisplay(_clan_summary(clan)))
                container.add_item(discord.ui.ActionRow(open_button))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        previous = discord.ui.Button(
            label="Назад",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            disabled=self.page == 0,
        )
        next_button = discord.ui.Button(
            label="Вперёд",
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= self.page_count - 1,
        )
        back = discord.ui.Button(
            label="Назад к кланам",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
        )

        async def previous_page(interaction: discord.Interaction) -> None:
            await self._show_page(interaction, self.page - 1)

        async def next_page(interaction: discord.Interaction) -> None:
            await self._show_page(interaction, self.page + 1)

        async def back_to_clans(interaction: discord.Interaction) -> None:
            await send_temporary(
                interaction,
                "Раздел кланов",
                view=ClanHubView(self.owner_id),
                ephemeral=True,
            )

        previous.callback = previous_page
        next_button.callback = next_page
        back.callback = back_to_clans
        container.add_item(discord.ui.ActionRow(previous, next_button, back))
        self.add_item(container)

    async def _show_page(self, interaction: discord.Interaction, page: int) -> None:
        view, files = await build_clan_list_view(
            self.owner_id, self.clans, own=self.own, page=page
        )
        await edit_temporary(
            interaction,
            content=None,
            embed=None,
            attachments=files,
            view=view,
        )


async def build_clan_list_view(
    owner_id: int, clans, *, own: bool = False, page: int = 0
) -> tuple[ClanListView, list[discord.File]]:
    """Build one safe V2 page and attach photos only for visible clans."""

    clans = list(clans)
    page_count = max(1, (len(clans) + CLANS_PER_PAGE - 1) // CLANS_PER_PAGE)
    page = max(0, min(page, page_count - 1))
    start = page * CLANS_PER_PAGE
    photo_files: dict[int, discord.File] = {}
    files: list[discord.File] = []
    for clan in clans[start : start + CLANS_PER_PAGE]:
        photo_path = await resolve_profile_photo(clan.photo, clan.photo_origin)
        if not photo_path:
            continue
        filename = f"clan-{clan.id}{photo_path.suffix}"
        file = discord.File(photo_path, filename=filename)
        photo_files[clan.id] = file
        files.append(file)
    return (
        ClanListView(
            owner_id,
            clans,
            own=own,
            page=page,
            photo_files=photo_files,
        ),
        files,
    )


class ClanGameSearchSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Игра",
            options=[
                discord.SelectOption(label=name, value=name) for name in GAME_LIST
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        game = self.values[0]
        if game in MMO_GAMES:
            await edit_temporary(
                interaction,
                content=f"Настройте поиск клана по **{game}**:",
                view=ClanSearchCriteriaView(interaction.user.id, game),
            )
            return
        clans = await platform_repository.search_clans(
            "discord", interaction.user.id, game
        )
        if not clans:
            await send_temporary(
                interaction, "Подходящих кланов пока нет.", ephemeral=True
            )
            return
        view, files = await build_clan_list_view(interaction.user.id, clans)
        await edit_temporary(
            interaction,
            content=None,
            embed=None,
            attachments=files,
            view=view,
        )


class ClanSearchFactionSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Фракция (необязательно)",
            options=[discord.SelectOption(label="Любая фракция", value="any")]
            + [
                discord.SelectOption(label=value, value=value)
                for value in AION_2_FACTIONS
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.faction = None if self.values[0] == "any" else self.values[0]
        await interaction.response.defer()


class ClanSearchCriteriaView(OwnedView):
    def __init__(self, owner_id: int, game: str):
        super().__init__(owner_id)
        self.game = game
        self.faction: str | None = None
        if game == "AION 2":
            self.add_item(ClanSearchFactionSelect())

    @discord.ui.button(
        label="Указать сервер и найти", style=discord.ButtonStyle.success
    )
    async def find(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ClanSearchFilterModal(self.game, self.faction)
        )


class ClanSearchFilterModal(TemporaryModal, title="Поиск клана"):
    server = discord.ui.TextInput(
        label="Сервер (необязательно)", required=False, max_length=100
    )
    faction = discord.ui.TextInput(
        label="Фракция (необязательно)", required=False, max_length=100
    )

    def __init__(self, game: str, faction: str | None):
        super().__init__()
        self.game = game
        self.selected_faction = faction
        if game == "AION 2":
            self.remove_item(self.faction)
        if faction:
            self.faction.default = faction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        faction = (
            self.selected_faction
            if self.game == "AION 2"
            else self.faction.value.strip() or None
        )
        if self.game == "AION 2" and faction and faction not in AION_2_FACTIONS:
            await send_temporary(
                interaction,
                "Фракция AION 2 должна быть «Элийцы» или «Асмодиане».",
                ephemeral=True,
            )
            return
        clans = await platform_repository.search_clans(
            "discord",
            interaction.user.id,
            self.game,
            server=self.server.value.strip() or None,
            faction=faction,
        )
        if not clans:
            await send_temporary(
                interaction, "Подходящих кланов пока нет.", ephemeral=True
            )
            return
        view, files = await build_clan_list_view(interaction.user.id, clans)
        await send_temporary(
            interaction,
            view=view,
            files=files,
            ephemeral=True,
        )


class ClanSearchView(OwnedView):
    def __init__(self, owner_id: int):
        super().__init__(owner_id)
        self.add_item(ClanGameSearchSelect())

    @discord.ui.button(label="Назад", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await edit_temporary(
            interaction, content="Раздел кланов", view=ClanHubView(self.owner_id)
        )
