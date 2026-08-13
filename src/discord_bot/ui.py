from dataclasses import dataclass, field

import discord

try:
    from config import settings
    from services.delivery import accept_instruction, deliver_text, reply_instruction
    from services.discord_statistics import discord_statistics
    from services.media import resolve_profile_photo
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
    from src.services.media import resolve_profile_photo
    from src.services.platform_repository import platform_repository
    from src.utils.constants import (
        AION_2_FACTIONS,
        CONVENIENT_TIME,
        GAME_LIST,
        GENDER_LIST,
        GOALS_LIST,
    )

from .formatting import clan_embed, platform_badge, profile_embed, score

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


class OwnedView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float | None = 900):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Эта приватная панель принадлежит другому пользователю.", ephemeral=True
            )
            return False
        return True


class ProfileBasicsModal(discord.ui.Modal, title="Анкета игрока"):
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

    def __init__(self, user_id: int, existing=None):
        super().__init__()
        self.user_id = user_id
        self.existing = existing
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
                await interaction.response.send_message(
                    "Возраст должен быть числом.", ephemeral=True
                )
                return
            if age < 13 or age > 120:
                await interaction.response.send_message(
                    "Укажите возраст от 13 до 120 лет.", ephemeral=True
                )
                return
        draft = ProfileDraft(
            nickname=self.nickname.value.strip(),
            age=age,
            about=self.about.value.strip(),
            gender=self.existing.gender if self.existing else None,
            games=[game.name for game in self.existing.games] if self.existing else [],
            goals=list(self.existing.goals or []) if self.existing else [],
            convenient_time=(
                list(self.existing.convenient_time or []) if self.existing else []
            ),
            ranks=(
                {game.name: game.rank for game in self.existing.games}
                if self.existing
                else {}
            ),
            game_details=(
                {
                    game.name: {"server": game.server, "faction": game.faction}
                    for game in self.existing.games
                }
                if self.existing
                else {}
            ),
        )
        await interaction.response.send_message(
            "Шаг 2 из 3: выберите параметры анкеты.",
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

    @discord.ui.button(
        label="Указать ранги и сохранить", style=discord.ButtonStyle.success
    )
    async def save(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if (
            not self.draft.games
            or not self.draft.goals
            or not self.draft.convenient_time
        ):
            await interaction.response.send_message(
                "Выберите хотя бы одну игру, цель поиска и удобное время.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(RanksModal(self.draft))


class RanksModal(discord.ui.Modal, title="Ранги и уровни"):
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
            await interaction.response.send_message(
                "Для AION 2 выберите фракцию и укажите сервер:",
                view=AionProfileDetailsView(interaction.user.id, self.draft),
                ephemeral=True,
            )
            return
        await send_profile_preview(interaction, self.draft)


async def send_profile_preview(
    interaction: discord.Interaction, draft: ProfileDraft
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
    await interaction.response.send_message(
        "Все верно?",
        embed=embed,
        view=ProfileConfirmView(interaction.user.id, draft),
        ephemeral=True,
    )


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
            await interaction.response.send_message(
                "Сначала выберите фракцию.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            AionProfileServerModal(self.draft, self.faction)
        )


class AionProfileServerModal(discord.ui.Modal, title="AION 2"):
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
        )
        await discord_statistics.record(
            interaction.user.id, str(interaction.user), "filled_profile"
        )
        await interaction.response.edit_message(
            content="Анкета создана. Разместить её в поиске?",
            embed=profile_embed(profile),
            view=ProfileVisibilityView(interaction.user.id),
        )

    @discord.ui.button(
        label="Исправить", emoji="✏️", style=discord.ButtonStyle.secondary
    )
    async def edit(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(ProfileBasicsModal(interaction.user.id))


class ProfileVisibilityView(OwnedView):
    @discord.ui.button(label="Да", style=discord.ButtonStyle.success)
    async def enable(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await platform_repository.set_profile_active(
            "discord", interaction.user.id, True
        )
        await interaction.response.edit_message(
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
        await interaction.response.edit_message(
            content="Анкета сохранена, но скрыта из поиска. Вернуть её можно командой `/pause`.",
            view=None,
        )


class ProfileDeleteConfirmView(OwnedView):
    @discord.ui.button(label="Да, удалить", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await platform_repository.delete_profile("discord", interaction.user.id)
        await interaction.response.edit_message(content="Анкета удалена.", view=None)

    @discord.ui.button(label="Нет", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="Удаление отменено.", view=None)


class MenuView(OwnedView):
    @discord.ui.button(
        label="Создать/изменить анкету", emoji="📝", style=discord.ButtonStyle.primary
    )
    async def form(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        profile = await platform_repository.get_profile("discord", interaction.user.id)
        await interaction.response.send_modal(
            ProfileBasicsModal(interaction.user.id, profile)
        )

    @discord.ui.button(
        label="Начать поиск", emoji="🔍", style=discord.ButtonStyle.success
    )
    async def search(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if not await platform_repository.get_profile("discord", interaction.user.id):
            await interaction.response.send_message(
                "Сначала создайте анкету через `/form`.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
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
            await interaction.response.send_message(
                "Анкета ещё не создана.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=profile_embed(profile), ephemeral=True
        )

    @discord.ui.button(label="Кланы", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def clans(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Раздел кланов", view=ClanHubView(interaction.user.id)
        )

    @discord.ui.button(
        label="Сайт GG.Store", emoji="🌐", style=discord.ButtonStyle.secondary
    )
    async def website(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await discord_statistics.record(
            interaction.user.id, str(interaction.user), "website"
        )
        await interaction.response.send_message(
            f"Перейти на сайт: {settings.WEBSITE_URL}", ephemeral=True
        )


class SearchModeView(OwnedView):
    @discord.ui.button(
        label="По критериям", emoji="🎯", style=discord.ButtonStyle.primary
    )
    async def filtered(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Выберите игру:",
            view=GameSearchView(interaction.user.id, filtered=True),
        )

    @discord.ui.button(
        label="Все анкеты", emoji="📋", style=discord.ButtonStyle.secondary
    )
    async def all_profiles(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Выберите игру:",
            view=GameSearchView(interaction.user.id, filtered=False),
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
        await discord_statistics.record(
            interaction.user.id, str(interaction.user), "start_search"
        )
        if self.filtered:
            await interaction.response.edit_message(
                content=f"Настройте поиск по **{game}**:",
                view=SearchCriteriaView(interaction.user.id, game),
            )
            return
        profiles = await platform_repository.search_profiles(
            viewer_platform="discord", viewer_user_id=interaction.user.id, game=game
        )
        if not profiles:
            await interaction.response.edit_message(
                content=f"По игре **{game}** пока нет активных анкет.",
                view=GameSearchView(interaction.user.id, filtered=False),
            )
            return
        await interaction.response.edit_message(
            content=f"Сейчас ищут напарников в **{game}**:",
            view=ProfileListView(interaction.user.id, profiles, game),
        )


class GameSearchView(OwnedView):
    def __init__(self, owner_id: int, filtered: bool = True):
        super().__init__(owner_id)
        self.add_item(GameSearchSelect(filtered))

    @discord.ui.button(label="В меню", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Меню TeamSeek", view=MenuView(self.owner_id)
        )


class GoalSearchSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Цель поиска (необязательно)",
            options=[discord.SelectOption(label="Любая цель", value="")]
            + [discord.SelectOption(label=value, value=value) for value in GOALS_LIST],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.goal = self.values[0] or None
        await interaction.response.defer()


class AionSearchFactionSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Фракция AION 2 (необязательно)",
            options=[discord.SelectOption(label="Любая фракция", value="")]
            + [
                discord.SelectOption(label=value, value=value)
                for value in AION_2_FACTIONS
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.faction = self.values[0] or None
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
        await interaction.response.edit_message(
            content="Выберите игру:", view=GameSearchView(self.owner_id, filtered=True)
        )


class SearchRankModal(discord.ui.Modal, title="Критерии поиска"):
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
            await interaction.response.send_message(
                "По выбранным критериям пока нет активных анкет. Попробуйте `/all`.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Подходящие анкеты по игре **{self.game}**:",
            view=ProfileListView(interaction.user.id, profiles, self.game),
            ephemeral=True,
        )


class ProfileResultSelect(discord.ui.Select):
    def __init__(self, profiles, page: int):
        start = page * 25
        options = []
        for profile in profiles[start : start + 25]:
            rating_values = [
                v for v in (profile.polite, profile.skill, profile.team_game) if v
            ]
            rating = sum(rating_values) / len(rating_values) if rating_values else None
            options.append(
                discord.SelectOption(
                    label=profile.nickname[:100],
                    value=str(profile.id),
                    description=f"{platform_badge(profile.platform)} • {score(rating)}"[
                        :100
                    ],
                )
            )
        super().__init__(placeholder="Открыть анкету", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        profile = await platform_repository.get_profile_by_id(int(self.values[0]))
        if not profile:
            await interaction.response.send_message(
                "Анкета больше недоступна.", ephemeral=True
            )
            return
        await discord_statistics.record(
            interaction.user.id, str(interaction.user), "open_profile"
        )
        view = self.view
        embed = profile_embed(profile, view.game)
        photo_path = await resolve_profile_photo(profile.photo, profile.photo_origin)
        kwargs = {
            "embed": embed,
            "view": ProfileActionsView(interaction.user.id, profile.id, view.game),
            "ephemeral": True,
        }
        if photo_path:
            file = discord.File(photo_path, filename=photo_path.name)
            embed.set_image(url=f"attachment://{photo_path.name}")
            kwargs["file"] = file
        await interaction.response.send_message(**kwargs)


class ProfileListView(OwnedView):
    def __init__(self, owner_id: int, profiles, game: str, page: int = 0):
        super().__init__(owner_id)
        self.profiles = profiles
        self.game = game
        self.page = page
        self.add_item(ProfileResultSelect(profiles, page))
        if page > 0:
            previous = discord.ui.Button(
                label="Назад", style=discord.ButtonStyle.secondary
            )
            previous.callback = self.previous_page
            self.add_item(previous)
        if (page + 1) * 25 < len(profiles):
            next_button = discord.ui.Button(
                label="Вперёд", style=discord.ButtonStyle.secondary
            )
            next_button.callback = self.next_page
            self.add_item(next_button)

    async def previous_page(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=ProfileListView(self.owner_id, self.profiles, self.game, self.page - 1)
        )

    async def next_page(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=ProfileListView(self.owner_id, self.profiles, self.game, self.page + 1)
        )


class ProfileActionsView(OwnedView):
    def __init__(self, owner_id: int, target_profile_id: int, game: str):
        super().__init__(owner_id)
        self.target_profile_id = target_profile_id
        self.game = game

    @discord.ui.button(
        label="Написать сообщение", emoji="✉️", style=discord.ButtonStyle.primary
    )
    async def message(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ContactMessageModal(self.target_profile_id, self.game)
        )

    @discord.ui.button(
        label="Пригласить в игру", emoji="🎮", style=discord.ButtonStyle.success
    )
    async def invite(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await send_contact(
            interaction, self.target_profile_id, self.game, "invite", None
        )


class ContactMessageModal(discord.ui.Modal, title="Сообщение игроку"):
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
        await interaction.response.send_message(
            "Одна из анкет больше недоступна.", ephemeral=True
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
        await interaction.response.send_message(
            "Сообщение отправлено. Ответ придёт в личные сообщения.", ephemeral=True
        )
        await discord_statistics.record(
            interaction.user.id, str(interaction.user), "invite_game"
        )
    else:
        await platform_repository.mark_contact_failed(request.id)
        await interaction.response.send_message(
            "Не удалось доставить сообщение: у пользователя могут быть закрыты личные сообщения. "
            "Попробуйте другую анкету.",
            ephemeral=True,
        )


class RatingModal(discord.ui.Modal, title="Оценить тиммейта"):
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
            await interaction.response.send_message(
                "Каждая оценка должна быть числом от 1 до 5.", ephemeral=True
            )
            return
        request = await platform_repository.get_contact_request(self.request_id)
        reviewer = await platform_repository.get_profile("discord", interaction.user.id)
        if not request or not reviewer or request.sender_profile_id != reviewer.id:
            await interaction.response.send_message(
                "Это приглашение вам недоступно.", ephemeral=True
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
            await interaction.response.send_message(str(exc), ephemeral=True)
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
        await interaction.response.send_message(
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
        await interaction.response.edit_message(
            content="Хорошо, вернёмся к вопросу позже. Оценить игрока можно командой `/rate`.",
            view=RatingPromptView(self.owner_id, self.request_id, in_process=True),
        )

    async def no(self, interaction: discord.Interaction) -> None:
        await platform_repository.set_contact_status(self.request_id, "declined")
        await interaction.response.edit_message(
            content="Понял. Оценка не требуется.", view=None
        )


class ClanHubView(OwnedView):
    @discord.ui.button(
        label="Создать клан", emoji="➕", style=discord.ButtonStyle.success
    )
    async def create(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Выберите игру и, для AION 2, фракцию:",
            view=ClanSetupView(interaction.user.id),
        )

    @discord.ui.button(label="Мои кланы", style=discord.ButtonStyle.secondary)
    async def own(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clans = await platform_repository.own_clans("discord", interaction.user.id)
        if not clans:
            await interaction.response.send_message(
                "У вас пока нет анкет кланов.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content="Ваши кланы:", view=ClanListView(interaction.user.id, clans)
        )

    @discord.ui.button(
        label="Найти клан", emoji="🔍", style=discord.ButtonStyle.primary
    )
    async def search(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Выберите игру:", view=ClanSearchView(interaction.user.id)
        )

    @discord.ui.button(label="В меню", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Меню TeamSeek", view=MenuView(self.owner_id)
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
        await interaction.response.defer()


class ClanSetupView(OwnedView):
    def __init__(self, owner_id: int):
        super().__init__(owner_id)
        self.game: str | None = None
        self.faction: str | None = None
        self.add_item(ClanChoiceSelect("game", "Игра", list(GAME_LIST)))
        self.add_item(ClanChoiceSelect("faction", "Фракция AION 2", AION_2_FACTIONS))

    @discord.ui.button(label="Продолжить", style=discord.ButtonStyle.success)
    async def continue_form(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if not self.game:
            await interaction.response.send_message(
                "Сначала выберите игру.", ephemeral=True
            )
            return
        if self.game == "AION 2" and not self.faction:
            await interaction.response.send_message(
                "Для AION 2 выберите фракцию.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ClanModal(self.game, self.faction))

    @discord.ui.button(label="Назад", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Раздел кланов", view=ClanHubView(self.owner_id)
        )


class ClanModal(discord.ui.Modal, title="Анкета клана"):
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

    def __init__(self, game: str, faction: str | None):
        super().__init__()
        self.game = game
        self.faction = faction
        if faction:
            self.faction_input.default = faction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        server = self.server.value.strip() or None
        faction = self.faction_input.value.strip() or self.faction
        if self.game in MMO_GAMES and (not server or not faction):
            await interaction.response.send_message(
                "Для этой MMO обязательно укажите сервер и фракцию.", ephemeral=True
            )
            return
        if self.game == "AION 2" and faction not in AION_2_FACTIONS:
            await interaction.response.send_message(
                "Для AION 2 выберите фракцию: Элийцы или Асмодиане.", ephemeral=True
            )
            return
        draft = {
            "name": self.name.value.strip(),
            "game": self.game,
            "description": self.description.value.strip(),
            "demands": self.demands.value.strip(),
            "server": server if self.game in MMO_GAMES else None,
            "faction": faction if self.game in MMO_GAMES else None,
        }
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
        await interaction.response.send_message(
            "Все верно?",
            embed=embed,
            view=ClanConfirmView(interaction.user.id, draft),
            ephemeral=True,
        )


class ClanConfirmView(OwnedView):
    def __init__(self, owner_id: int, draft: dict[str, str | None]):
        super().__init__(owner_id)
        self.draft = draft

    @discord.ui.button(label="Все верно", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        clan = await platform_repository.create_clan(
            platform="discord", user_id=interaction.user.id, **self.draft
        )
        await interaction.response.edit_message(
            content=(
                f"Анкета клана создана. Аватар можно добавить командой "
                f"`/clan_photo clan_id:{clan.id}`."
            ),
            embed=clan_embed(clan),
            view=None,
        )

    @discord.ui.button(
        label="Исправить", emoji="✏️", style=discord.ButtonStyle.secondary
    )
    async def edit(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ClanModal(str(self.draft["game"]), self.draft["faction"])
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
            await interaction.response.send_message(
                "Анкета клана не найдена.", ephemeral=True
            )
            return
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
            file = discord.File(photo_path, filename=photo_path.name)
            embed.set_image(url=f"attachment://{photo_path.name}")
            kwargs["file"] = file
        await interaction.response.send_message(**kwargs)


class OwnClanActionsView(OwnedView):
    def __init__(self, owner_id: int, clan):
        super().__init__(owner_id)
        self.clan = clan

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
        await interaction.response.send_message(
            "Выберите новую игру:",
            view=ClanGameEditView(interaction.user.id, self.clan),
            ephemeral=True,
        )

    @discord.ui.button(label="Удалить", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content=f"Удалить анкету клана **{self.clan.name}**?",
            view=ClanDeleteConfirmView(interaction.user.id, self.clan.id),
        )


class ClanEditModal(discord.ui.Modal, title="Изменить клан"):
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

    async def on_submit(self, interaction: discord.Interaction) -> None:
        server = self.server.value.strip() or None
        faction = self.faction.value.strip() or None
        if self.clan.game in MMO_GAMES and (not server or not faction):
            await interaction.response.send_message(
                "Для этой MMO обязательны сервер и фракция.", ephemeral=True
            )
            return
        if self.clan.game == "AION 2" and faction not in AION_2_FACTIONS:
            await interaction.response.send_message(
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
        await interaction.response.send_message(
            "Анкета клана обновлена.", embed=clan_embed(clan), ephemeral=True
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
        await interaction.response.edit_message(
            content="Игра клана обновлена.", embed=clan_embed(clan), view=None
        )


class ClanGameEditView(OwnedView):
    def __init__(self, owner_id: int, clan):
        super().__init__(owner_id)
        self.clan = clan
        self.add_item(ClanGameEditSelect())


class ClanGameChangeModal(discord.ui.Modal, title="Новая MMO"):
    server = discord.ui.TextInput(label="Сервер", min_length=1, max_length=100)
    faction = discord.ui.TextInput(label="Фракция", min_length=1, max_length=100)

    def __init__(self, clan, game: str):
        super().__init__()
        self.clan = clan
        self.game = game

    async def on_submit(self, interaction: discord.Interaction) -> None:
        faction = self.faction.value.strip()
        if self.game == "AION 2" and faction not in AION_2_FACTIONS:
            await interaction.response.send_message(
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
        await interaction.response.send_message(
            "Игра клана обновлена.", embed=clan_embed(clan), ephemeral=True
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
        await interaction.response.edit_message(
            content="Анкета клана удалена." if deleted else "Анкета клана не найдена.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Нет", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        clan = await platform_repository.get_clan_by_id(self.clan_id)
        await interaction.response.edit_message(
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


class ClanApplicationModal(discord.ui.Modal, title="Заявка в клан"):
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
            await interaction.response.send_message(
                "Клан или ваша анкета больше недоступны.", ephemeral=True
            )
            return
        leader = await platform_repository.get_profile(clan.platform, clan.user_id)
        if not leader:
            await interaction.response.send_message(
                "Анкета лидера клана недоступна.", ephemeral=True
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
        await interaction.response.send_message(
            "Заявка отправлена."
            if result.delivered
            else "Не удалось доставить заявку лидеру.",
            ephemeral=True,
        )


class ClanListView(OwnedView):
    def __init__(self, owner_id: int, clans):
        super().__init__(owner_id)
        self.clans = clans
        self.add_item(ClanResultSelect(clans))


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
            await interaction.response.edit_message(
                content=f"Настройте поиск клана по **{game}**:",
                view=ClanSearchCriteriaView(interaction.user.id, game),
            )
            return
        clans = await platform_repository.search_clans(
            "discord", interaction.user.id, game
        )
        if not clans:
            await interaction.response.send_message(
                "Подходящих кланов пока нет.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=f"Кланы по игре **{game}**:",
            view=ClanListView(interaction.user.id, clans),
        )


class ClanSearchFactionSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Фракция (необязательно)",
            options=[discord.SelectOption(label="Любая фракция", value="")]
            + [
                discord.SelectOption(label=value, value=value)
                for value in AION_2_FACTIONS
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.faction = self.values[0] or None
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


class ClanSearchFilterModal(discord.ui.Modal, title="Поиск клана"):
    server = discord.ui.TextInput(
        label="Сервер (необязательно)", required=False, max_length=100
    )
    faction = discord.ui.TextInput(
        label="Фракция (необязательно)", required=False, max_length=100
    )

    def __init__(self, game: str, faction: str | None):
        super().__init__()
        self.game = game
        if faction:
            self.faction.default = faction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        faction = self.faction.value.strip() or None
        if self.game == "AION 2" and faction and faction not in AION_2_FACTIONS:
            await interaction.response.send_message(
                "Фракция AION 2 должна быть «Элийцы» или «Асмодиане».", ephemeral=True
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
            await interaction.response.send_message(
                "Подходящих кланов пока нет.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Подходящие кланы по игре **{self.game}**:",
            view=ClanListView(interaction.user.id, clans),
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
        await interaction.response.edit_message(
            content="Раздел кланов", view=ClanHubView(self.owner_id)
        )
