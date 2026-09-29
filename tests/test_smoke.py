import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


DEFAULT_ENV = {
    "TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
    "DB_NAME": "test",
    "DB_USER": "test",
    "DB_PASSWORD": "test",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "5432",
    "DB_DRIVER": "asyncpg",
    "GOOGLE_SHEET_CREDENTIALS_PATH": "/tmp/missing.json",
    "GOOGLE_SHEET_ID": "test",
    "GOOGLE_SHEET_WORKSHEET_NAME": "Telegram",
    "PRIVATE_PHOTO_GROUP_ID": "1",
    "PRIMARY_GUILD_ID": "1414672367476805794",
}
for key, value in DEFAULT_ENV.items():
    os.environ.setdefault(key, value)


class SmokeTests(unittest.TestCase):
    def test_google_sheet_short_rows_do_not_match_or_crash(self):
        from google_sheet import GoogleSheetService

        class Worksheet:
            @staticmethod
            def get_all_values():
                return [["8334693279"], ["8334693279", "name", "campaign"]]

        service = GoogleSheetService.__new__(GoogleSheetService)
        service.worksheet = Worksheet()

        self.assertEqual(
            service.get_row_index_multi({0: "8334693279", 2: "campaign"}), 2
        )
        self.assertIsNone(service.get_row_index_multi({0: "8334693279", 3: "missing"}))

    def test_telegram_routers_load(self):
        from handlers import routers

        self.assertGreaterEqual(len(routers), 20)

    def test_discord_commands_load(self):
        from discord_bot.bot import bot

        names = {command.name for command in bot.tree.get_commands()}
        self.assertTrue(
            {
                "menu",
                "panel",
                "form",
                "edit",
                "profile",
                "search",
                "all",
                "clan",
                "photo",
                "pause",
                "delete_profile",
                "reply",
                "rate",
                "accept",
                "clan_photo",
            }.issubset(names)
        )

    def test_aion_is_available(self):
        from utils.constants import AION_2_FACTIONS, GAME_LIST

        self.assertIn("AION 2", GAME_LIST)
        self.assertEqual(AION_2_FACTIONS, ["Элийцы", "Асмодиане"])

    def test_shared_schema_is_mapped(self):
        from models.interaction import ContactRequest, ExperienceEvent, Review
        from models.profile import Game, Profile

        self.assertIn("platform", Profile.__table__.columns)
        self.assertIn("age", Profile.__table__.columns)
        self.assertEqual(ContactRequest.__tablename__, "contact_requests")
        self.assertEqual(Review.__tablename__, "profile_reviews")
        self.assertEqual(ExperienceEvent.__tablename__, "experience_events")
        self.assertIn("server", Game.__table__.columns)
        self.assertIn("faction", Game.__table__.columns)

    def test_tz_discord_views(self):
        import asyncio

        async def check():
            from discord_bot.ui import (
                ClanHubView,
                ClanSearchCriteriaView,
                ClanSetupView,
                GameSearchSelect,
                GameSearchView,
                MenuView,
                ProfileDraft,
                ProfileOptionsView,
                ProfileRanksView,
                RatingPromptView,
                SearchCriteriaView,
            )

            filtered = GameSearchView(1, filtered=True)
            all_profiles = GameSearchView(1, filtered=False)
            self.assertTrue(
                next(
                    item
                    for item in filtered.children
                    if isinstance(item, GameSearchSelect)
                ).filtered
            )
            self.assertFalse(
                next(
                    item
                    for item in all_profiles.children
                    if isinstance(item, GameSearchSelect)
                ).filtered
            )
            labels = {item.label for item in RatingPromptView(1, 42).children}
            self.assertEqual(labels, {"Да", "В процессе", "Нет"})
            draft = ProfileDraft(nickname="Test", age=None, about="About")
            for view in (
                MenuView(1, has_profile=True),
                ProfileOptionsView(1, draft),
                ProfileRanksView(1, draft),
                SearchCriteriaView(1, "AION 2"),
                ClanHubView(1),
                ClanSetupView(1),
                ClanSearchCriteriaView(1, "AION 2"),
            ):
                self.assertLessEqual(len(view.children), 25)
                for component in view.to_components():
                    for item in component["components"]:
                        for option in item.get("options", []):
                            self.assertTrue(option["value"])

        asyncio.run(check())

    def test_discord_dynamic_menu(self):
        from discord_bot.ui import MenuView

        new_user_labels = {
            item.label for item in MenuView(1, has_profile=False).children
        }
        existing_labels = {
            item.label for item in MenuView(1, has_profile=True).children
        }

        self.assertEqual(new_user_labels, {"Создать анкету", "Сайт GG.Store"})
        self.assertEqual(
            existing_labels,
            {"Начать поиск", "Моя анкета", "Кланы", "Сайт GG.Store"},
        )

    def test_discord_navigation_buttons(self):
        from discord_bot.ui import (
            ClanListView,
            GameSearchView,
            MyProfileView,
            OwnClanActionsView,
            SearchModeView,
        )

        clan = SimpleNamespace(
            id=10,
            name="Clan",
            game="AION 2",
            platform="discord",
            description="Description",
            server="Siel",
            faction="Элийцы",
            photo=None,
            photo_origin=None,
            user_id=1,
        )
        profile = SimpleNamespace(id=20)
        expected = (
            (SearchModeView(1), "В меню"),
            (GameSearchView(1), "Назад"),
            (GameSearchView(1), "В меню"),
            (MyProfileView(1, profile), "В меню"),
            (ClanListView(1, [clan], own=True), "Назад к кланам"),
            (OwnClanActionsView(1, clan), "Назад к кланам"),
        )
        for view, label in expected:
            self.assertIn(
                label,
                {getattr(item, "label", None) for item in view.walk_children()},
            )

    def test_profile_rank_step_and_skip(self):
        import asyncio

        from discord_bot.ui import (
            AionProfileDetailsView,
            ProfileDraft,
            ProfileRanksView,
        )

        async def check():
            draft = ProfileDraft(
                nickname="Test", age=None, about="About", games=["Dota 2"]
            )
            view = ProfileRanksView(1, draft)
            self.assertEqual(
                {item.label for item in view.children},
                {"Указать ранги", "Пропустить ранги"},
            )
            interaction = SimpleNamespace(
                user=SimpleNamespace(id=1),
                response=SimpleNamespace(edit_message=AsyncMock()),
            )
            skip = next(
                item for item in view.children if item.label == "Пропустить ранги"
            )
            with patch(
                "discord_bot.ui.send_profile_preview", new=AsyncMock()
            ) as preview:
                await skip.callback(interaction)
            self.assertEqual(draft.ranks, {"Dota 2": None})
            preview.assert_awaited_once_with(interaction, draft, edit=True)

            aion_draft = ProfileDraft(
                nickname="Test", age=None, about="About", games=["AION 2"]
            )
            aion_view = ProfileRanksView(1, aion_draft)
            aion_interaction = SimpleNamespace(
                user=SimpleNamespace(id=1),
                response=SimpleNamespace(edit_message=AsyncMock()),
            )
            aion_skip = next(
                item for item in aion_view.children if item.label == "Пропустить ранги"
            )
            await aion_skip.callback(aion_interaction)
            next_view = aion_interaction.response.edit_message.await_args.kwargs["view"]
            self.assertIsInstance(next_view, AionProfileDetailsView)
            self.assertEqual(aion_draft.ranks, {"AION 2": None})

        asyncio.run(check())

    def test_profile_catalogue_uses_v2_cards_and_safe_pagination(self):
        import asyncio
        import discord

        from discord_bot.ui import (
            PROFILES_PER_PAGE,
            ContactMessageModal,
            ProfileActionsView,
            ProfileListView,
            send_profile_details,
        )

        profiles = [
            SimpleNamespace(
                id=index,
                nickname=f"Игрок {index}",
                platform="discord" if index % 2 else "telegram",
                age=20 + index,
                experience=index * 100,
                about=f"Описание игрока {index}",
                goals=["Рейтинг"],
                photo=None,
                photo_origin=None,
                games=[
                    SimpleNamespace(
                        name="AION 2",
                        rank=f"Ранг {index}",
                        server="Siel",
                        faction="Элийцы",
                    )
                ],
            )
            for index in range(1, 13)
        ]
        first = ProfileListView(1, profiles, "AION 2", filtered=False)
        last = ProfileListView(1, profiles, "AION 2", filtered=False, page=2)

        self.assertIsInstance(first, discord.ui.LayoutView)
        self.assertEqual(PROFILES_PER_PAGE, 5)
        self.assertEqual(first.page_count, 3)
        self.assertLessEqual(first.total_children_count, 40)
        self.assertLessEqual(last.total_children_count, 40)
        first_buttons = [
            item
            for item in first.walk_children()
            if isinstance(item, discord.ui.Button)
        ]
        self.assertTrue(
            {f"Игрок {index}" for index in range(1, 6)}.issubset(
                {item.label for item in first_buttons}
            )
        )
        self.assertEqual(
            {
                item.label
                for item in last.walk_children()
                if isinstance(item, discord.ui.Button)
            }
            & {f"Игрок {index}" for index in range(1, 13)},
            {"Игрок 11", "Игрок 12"},
        )
        self.assertTrue(
            next(item for item in first_buttons if item.label == "Назад").disabled
        )
        self.assertTrue(
            next(
                item
                for item in last.walk_children()
                if isinstance(item, discord.ui.Button) and item.label == "Вперёд"
            ).disabled
        )

        async def check_actions():
            navigation_response = SimpleNamespace(
                send_message=AsyncMock(return_value=SimpleNamespace(message_id=100))
            )
            navigation_interaction = SimpleNamespace(
                user=SimpleNamespace(id=1),
                response=navigation_response,
                delete_original_response=AsyncMock(),
            )
            games = next(
                item for item in first_buttons if item.label == "К выбору игры"
            )
            await games.callback(navigation_interaction)
            navigation_response.send_message.assert_awaited_once()
            navigation_call = navigation_response.send_message.await_args
            self.assertEqual(navigation_call.args[0], "Выберите игру:")
            self.assertTrue(navigation_call.kwargs["ephemeral"])

            response = SimpleNamespace(send_modal=AsyncMock())
            interaction = SimpleNamespace(user=SimpleNamespace(id=1), response=response)
            actions = ProfileActionsView(1, profiles[5].id, "AION 2")
            message = next(
                item for item in actions.children if item.label == "Написать"
            )
            await message.callback(interaction)
            modal = response.send_modal.await_args.args[0]
            self.assertIsInstance(modal, ContactMessageModal)
            self.assertEqual(modal.target_profile_id, 6)

            invite = next(
                item for item in actions.children if item.label == "Пригласить"
            )
            with patch("discord_bot.ui.send_contact", new=AsyncMock()) as send:
                await invite.callback(interaction)
            send.assert_awaited_once_with(interaction, 6, "AION 2", "invite", None)

            details_response = SimpleNamespace(defer=AsyncMock())
            details_followup = SimpleNamespace(send=AsyncMock())
            details_interaction = SimpleNamespace(
                user=SimpleNamespace(id=1),
                response=details_response,
                followup=details_followup,
            )
            current = SimpleNamespace(
                id=6, is_active=True, photo=None, photo_origin=None
            )
            repository = SimpleNamespace(
                get_profile_by_id=AsyncMock(return_value=current)
            )
            statistics = SimpleNamespace(record=AsyncMock())
            with (
                patch("discord_bot.ui.platform_repository", new=repository),
                patch("discord_bot.ui.profile_embed"),
                patch(
                    "discord_bot.ui.resolve_profile_photo",
                    new=AsyncMock(return_value=None),
                ),
                patch("discord_bot.ui.discord_statistics", new=statistics),
            ):
                await send_profile_details(details_interaction, profiles[5], "AION 2")
                await asyncio.sleep(0)
            details_response.defer.assert_awaited_once_with(
                ephemeral=True, thinking=True
            )
            details_followup.send.assert_awaited_once()

        asyncio.run(check_actions())

    def test_public_panel_is_persistent(self):
        import discord

        from discord_bot.ui import PublicPanelView

        view = PublicPanelView()
        self.assertIsNone(view.timeout)
        self.assertTrue(view.is_persistent())
        children = list(view.walk_children())
        buttons = [item for item in children if isinstance(item, discord.ui.Button)]
        self.assertEqual(
            {item.label for item in buttons},
            {
                "Начать поиск",
                "Моя анкета",
                "Кланы",
                "Сайт GG.Store",
            },
        )
        self.assertEqual(
            {item.custom_id for item in buttons},
            set(PublicPanelView.CUSTOM_IDS.values()) - {PublicPanelView.CUSTOM_ID},
        )
        self.assertTrue(
            any(isinstance(item, discord.ui.Container) for item in children)
        )
        self.assertTrue(
            any(isinstance(item, discord.ui.TextDisplay) for item in children)
        )

    def test_clan_catalogue_uses_v2_cards_and_safe_pagination(self):
        import discord

        from discord_bot.ui import CLANS_PER_PAGE, ClanListView

        clans = [
            SimpleNamespace(
                id=index,
                name=f"Клан {index}",
                game="AION 2",
                platform="discord" if index % 2 else "telegram",
                description=f"Описание клана {index}",
                server="Siel",
                faction="Элийцы",
                photo=None,
                photo_origin=None,
                user_id=index,
            )
            for index in range(1, 13)
        ]
        first = ClanListView(1, clans)
        last = ClanListView(1, clans, page=2)

        self.assertIsInstance(first, discord.ui.LayoutView)
        self.assertEqual(CLANS_PER_PAGE, 5)
        self.assertEqual(first.page_count, 3)
        self.assertLessEqual(first.total_children_count, 40)
        self.assertLessEqual(last.total_children_count, 40)
        first_buttons = [
            item
            for item in first.walk_children()
            if isinstance(item, discord.ui.Button)
        ]
        self.assertTrue(
            {f"Клан {index}" for index in range(1, 6)}.issubset(
                {item.label for item in first_buttons}
            )
        )
        self.assertEqual(
            {
                item.label
                for item in last.walk_children()
                if isinstance(item, discord.ui.Button)
            }
            & {f"Клан {index}" for index in range(1, 13)},
            {"Клан 11", "Клан 12"},
        )
        self.assertTrue(
            next(item for item in first_buttons if item.label == "Назад").disabled
        )
        self.assertTrue(
            next(
                item
                for item in last.walk_children()
                if isinstance(item, discord.ui.Button) and item.label == "Вперёд"
            ).disabled
        )

    def test_discord_analytics_contract(self):
        from services.discord_statistics import DiscordStatistics

        self.assertEqual(DiscordStatistics.columns["website"], 7)
        self.assertEqual(DiscordStatistics.columns["last_activity"], 8)


if __name__ == "__main__":
    unittest.main()
