import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import tests.test_smoke  # noqa: F401 -- initialise isolated test settings
from discord_bot import ui
from discord_bot.messages import temporary_messages


class FormRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await temporary_messages.close()

    async def test_clan_game_selection_stays_visible_after_view_update(self):
        view = ui.ClanSetupView(1)
        interaction = SimpleNamespace(
            response=SimpleNamespace(edit_message=AsyncMock(), defer=AsyncMock())
        )
        game = next(
            item for item in view.children if isinstance(item, ui.ClanChoiceSelect)
        )
        game._values = ["AION 2"]
        await game.callback(interaction)
        self.assertEqual(view.game, "AION 2")
        self.assertEqual(
            [
                option["value"]
                for option in game.to_component_dict()["options"]
                if option["default"]
            ],
            ["AION 2"],
        )
        faction = next(
            item
            for item in view.children
            if isinstance(item, ui.ClanChoiceSelect) and item.field_name == "faction"
        )
        faction._values = [ui.AION_2_FACTIONS[0]]
        await faction.callback(interaction)
        self.assertEqual(
            [option.value for option in game.options if option.default], ["AION 2"]
        )
        game._values = ["PUBG"]
        await game.callback(interaction)
        self.assertEqual(
            [option.value for option in game.options if option.default], ["PUBG"]
        )
        self.assertIsNone(view.faction)
        self.assertNotIn(faction, view.children)

    async def test_clan_confirm_correction_preserves_long_text(self):
        draft = dict(
            name="Test",
            game="AION 2",
            description="Д" * 1500,
            demands="Т" * 1000,
            server="Европа",
            faction="Элийцы",
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1), response=SimpleNamespace(send_modal=AsyncMock())
        )
        await ui.ClanConfirmView(1, draft).edit.callback(interaction)
        modal = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(modal.description.default, draft["description"])
        self.assertEqual(modal.demands.default, draft["demands"])
        self.assertEqual(modal.server.default, "Европа")
        self.assertEqual(modal.faction, "Элийцы")

    async def test_clan_confirm_acknowledges_before_save_and_prevents_duplicate(self):
        import asyncio

        draft = dict(
            name="Test",
            game="AION 2",
            description="D",
            demands="T",
            server="Европа",
            faction="Элийцы",
        )
        clan = SimpleNamespace(id=80, platform="discord", **draft)
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1), response=SimpleNamespace(defer=AsyncMock())
        )

        async def create(**kwargs):
            self.assertGreater(interaction.response.defer.await_count, 0)
            return clan

        repository = SimpleNamespace(create_clan=AsyncMock(side_effect=create))
        view = ui.ClanConfirmView(1, draft)
        with (
            patch.object(ui, "platform_repository", repository),
            patch.object(ui, "followup_temporary", new=AsyncMock()),
        ):
            await asyncio.gather(
                view.confirm.callback(interaction), view.confirm.callback(interaction)
            )
        repository.create_clan.assert_awaited_once()
        self.assertIs(view._created_clan, clan)

    async def test_clan_save_failure_explains_error_and_keeps_draft(self):
        from sqlalchemy.exc import SQLAlchemyError

        draft = dict(
            name="Test",
            game="AION 2",
            description="D",
            demands="T",
            server="Европа",
            faction="Элийцы",
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1), response=SimpleNamespace(defer=AsyncMock())
        )
        repository = SimpleNamespace(
            create_clan=AsyncMock(side_effect=SQLAlchemyError("test"))
        )
        view = ui.ClanConfirmView(1, draft)
        with (
            patch.object(ui, "platform_repository", repository),
            patch.object(ui, "followup_temporary", new=AsyncMock()) as reply,
            self.assertLogs("discord_bot.ui", level="ERROR"),
        ):
            await view.confirm.callback(interaction)
        self.assertIn("Не удалось", reply.await_args.args[1])
        self.assertEqual(view.draft, draft)
        self.assertIsNone(view._created_clan)

    async def test_correction_keeps_draft_and_goes_directly_to_preview(self):
        draft = ui.ProfileDraft(
            nickname="Player",
            age=25,
            about="About",
            games=["Dota 2"],
            goals=["Своя цель"],
            convenient_time=["После работы"],
            ranks={"Dota 2": "Gold"},
            is_active=False,
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1), response=SimpleNamespace(send_modal=AsyncMock())
        )
        view = ui.ProfileConfirmView(1, draft)
        await view.edit.callback(interaction)
        modal = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(modal.nickname.default, "Player")
        self.assertEqual(len(modal.children), 3)
        self.assertFalse(hasattr(modal, "goals_text"))
        for item in modal.children:
            item._value = item.default or ""
        with patch.object(ui, "send_profile_preview", new=AsyncMock()) as preview:
            await modal.on_submit(interaction)
            preview.assert_awaited_once_with(interaction, draft)
        self.assertEqual(draft.ranks, {"Dota 2": "Gold"})
        self.assertFalse(draft.is_active)
        options = ui.ProfileOptionsView(1, draft)
        goals = next(
            item
            for item in options.children
            if isinstance(item, ui.DraftSelect) and item.field_name == "goals"
        )
        self.assertEqual([option.value for option in goals.options], ui.GOALS_LIST)
        self.assertEqual(draft.goals, ["Своя цель"])
        self.assertEqual(draft.convenient_time, ["После работы"])

    async def test_skip_preserves_existing_ranks(self):
        draft = ui.ProfileDraft(
            nickname="P",
            age=None,
            about="A",
            games=["Dota 2"],
            ranks={"Dota 2": "Gold"},
        )
        with patch.object(ui, "send_profile_preview", new=AsyncMock()):
            await ui.ProfileRanksView(1, draft).skip.callback(SimpleNamespace())
        self.assertEqual(draft.ranks["Dota 2"], "Gold")

    async def test_clan_fields_match_game_and_search_does_not_repeat_faction(self):
        casual = ui.ClanModal("PUBG", None)
        self.assertNotIn(casual.server, casual.children)
        self.assertNotIn(casual.faction_input, casual.children)
        aion = ui.ClanModal(
            "AION 2",
            "Элийцы",
            draft={
                "name": "Test",
                "description": "Details",
                "demands": "Rules",
                "server": "Siel",
            },
        )
        self.assertTrue(aion.server.required)
        self.assertEqual(aion.server.default, "Siel")
        self.assertEqual(aion.description.default, "Details")
        self.assertNotIn(aion.faction_input, aion.children)
        search = ui.ClanSearchFilterModal("AION 2", "Элийцы")
        self.assertNotIn(search.faction, search.children)
        response = SimpleNamespace(
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=100))
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1),
            response=response,
            delete_original_response=AsyncMock(),
        )
        repository = SimpleNamespace(search_clans=AsyncMock(return_value=[]))
        with patch.object(ui, "platform_repository", repository):
            await search.on_submit(interaction)
        repository.search_clans.assert_awaited_once_with(
            "discord", 1, "AION 2", server=None, faction="Элийцы"
        )

    async def test_avatar_command_opens_file_picker_without_attachment(self):
        from discord_bot.bot import clan_photo

        interaction = SimpleNamespace(response=SimpleNamespace(send_modal=AsyncMock()))
        with patch("discord_bot.bot.primary_member", new=AsyncMock(return_value=True)):
            await clan_photo.callback(interaction, 80)
        modal = interaction.response.send_modal.await_args.args[0]
        self.assertIsInstance(modal, ui.ClanAvatarModal)
        self.assertEqual(modal.clan_id, 80)
        self.assertTrue(modal.upload.required)
        modal.to_components()

    async def test_avatar_upload_checks_owner_and_saves_image(self):
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1), response=SimpleNamespace(defer=AsyncMock())
        )
        upload = SimpleNamespace(
            content_type="image/png",
            size=12,
            filename="avatar.png",
            read=AsyncMock(return_value=b"image"),
        )
        repository = SimpleNamespace(
            get_clan_by_id=AsyncMock(
                return_value=SimpleNamespace(platform="discord", user_id=2)
            ),
            update_clan_photo=AsyncMock(return_value=True),
        )
        with (
            patch.object(ui, "platform_repository", repository),
            patch.object(ui, "followup_temporary", new=AsyncMock()),
            patch.object(
                ui, "store_image", new=AsyncMock(return_value="/media/avatar.png")
            ) as store,
        ):
            await ui.save_clan_avatar(interaction, 80, upload)
            store.assert_not_awaited()
            repository.get_clan_by_id.return_value.user_id = 1
            await ui.save_clan_avatar(interaction, 80, upload)
            repository.update_clan_photo.assert_awaited_once_with(
                80, "discord", 1, "/media/avatar.png", "local"
            )

    async def test_invalid_clan_retains_entered_fields_for_retry(self):
        modal = ui.ClanModal("AION 2", "Элийцы")
        modal.name._value = "Test clan"
        modal.description._value = "Long description"
        modal.demands._value = "Requirements"
        modal.server._value = "   "
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1),
            response=SimpleNamespace(
                send_message=AsyncMock(return_value=SimpleNamespace(message_id=100)),
                send_modal=AsyncMock(),
            ),
            delete_original_response=AsyncMock(),
        )
        await modal.on_submit(interaction)
        retry = interaction.response.send_message.await_args.kwargs["view"]
        await retry.retry.callback(interaction)
        restored = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(restored.name.default, "Test clan")
        self.assertEqual(restored.description.default, "Long description")
        self.assertEqual(restored.demands.default, "Requirements")
