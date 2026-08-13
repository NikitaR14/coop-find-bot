import os
import unittest


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
        self.assertIsNone(
            service.get_row_index_multi({0: "8334693279", 3: "missing"})
        )

    def test_telegram_routers_load(self):
        from handlers import routers

        self.assertGreaterEqual(len(routers), 20)

    def test_discord_commands_load(self):
        from discord_bot.bot import bot

        names = {command.name for command in bot.tree.get_commands()}
        self.assertTrue(
            {
                "menu",
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
                MenuView(1),
                ProfileOptionsView(1, draft),
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

    def test_discord_analytics_contract(self):
        from services.discord_statistics import DiscordStatistics

        self.assertEqual(DiscordStatistics.columns["website"], 7)
        self.assertEqual(DiscordStatistics.columns["last_activity"], 8)


if __name__ == "__main__":
    unittest.main()
