import io
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
import tests.test_smoke  # noqa: F401 -- isolated settings
from discord_bot import ui
from discord_bot.bot import panel
from discord_bot.messages import temporary_messages


def profile(index=1):
    return NS(
        id=index,
        nickname=f"Player {index}",
        age=25,
        about="About",
        gender=None,
        platform="discord",
        experience=0,
        goals=["Legacy goal"],
        convenient_time=["Legacy time"],
        is_active=False,
        games=[NS(name="AION 2", rank="50", server="Siel", faction="Элийцы")],
        photo=None,
        photo_origin=None,
    )


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await temporary_messages.close()

    async def test_profile_buttons_always_below_description_with_and_without_photos(
        self,
    ):
        profiles = [profile(i) for i in range(1, 7)]
        photo = discord.File(io.BytesIO(b"image"), filename="avatar.png")
        self.addCleanup(photo.close)
        for page in (0, 1):
            view = ui.ProfileListView(
                1, profiles, "AION 2", filtered=False, page=page, photo_files={1: photo}
            )
            container = view.children[0]
            for child in container.children:
                if isinstance(child, discord.ui.Section):
                    self.assertIsInstance(child.accessory, discord.ui.Thumbnail)
            expected = profiles[page * 5 : page * 5 + 5]
            for selected in expected:
                row = next(
                    child
                    for child in container.children
                    if isinstance(child, discord.ui.ActionRow)
                    and child.children[0].label == selected.nickname
                )
                predecessor = container.children[container.children.index(row) - 1]
                self.assertIsInstance(
                    predecessor, (discord.ui.TextDisplay, discord.ui.Section)
                )
                with patch.object(
                    ui, "send_profile_details", new=AsyncMock()
                ) as details:
                    await row.children[0].callback(NS())
                self.assertIs(details.await_args.args[1], selected)
            self.assertLessEqual(view.total_children_count, 40)
            view.to_components()

    async def test_unavailable_photo_uses_text_and_button_row(self):
        player = profile()
        player.photo = "missing.png"
        with patch.object(
            ui, "resolve_profile_photo", new=AsyncMock(return_value=None)
        ):
            view, files = await ui.build_profile_list_view(
                1, [player], "AION 2", filtered=False
            )
        self.assertEqual(files, [])
        self.assertFalse(
            any(isinstance(item, discord.ui.Section) for item in view.walk_children())
        )
        self.assertTrue(
            any(
                isinstance(item, discord.ui.Button) and item.label == player.nickname
                for item in view.walk_children()
            )
        )

    async def test_photo_download_failure_does_not_hide_profile(self):
        player = profile()
        with (
            patch.object(
                ui, "resolve_profile_photo", new=AsyncMock(side_effect=TimeoutError())
            ),
            self.assertLogs("discord_bot.ui", level="WARNING"),
        ):
            view, files = await ui.build_profile_list_view(
                1, [player], "AION 2", filtered=False
            )
        self.assertEqual(files, [])
        self.assertTrue(
            any(
                isinstance(item, discord.ui.Button) and item.label == player.nickname
                for item in view.walk_children()
            )
        )

    async def test_old_values_survive_basics_edit_then_only_selected_field_changes(
        self,
    ):
        player = profile()
        modal = ui.ProfileBasicsModal(1, existing=player)
        self.assertEqual(
            [item.label for item in modal.children],
            ["Никнейм", "Возраст (необязательно)", "О себе"],
        )
        for item in modal.children:
            item._value = item.default or ""
        modal.nickname._value = "Renamed"
        event = NS(user=NS(id=1), response=NS(defer=AsyncMock()))
        with patch.object(ui, "send_profile_preview", new=AsyncMock()) as preview:
            await modal.on_submit(event)
        draft = preview.await_args.args[1]
        self.assertEqual(draft.nickname, "Renamed")
        self.assertEqual(draft.goals, ["Legacy goal"])
        self.assertEqual(draft.convenient_time, ["Legacy time"])
        view = ui.ProfileOptionsView(1, draft)
        selects = {
            item.field_name: item
            for item in view.children
            if isinstance(item, ui.DraftSelect)
        }
        self.assertEqual(
            [option.value for option in selects["goals"].options], ui.GOALS_LIST
        )
        self.assertEqual(
            [option.value for option in selects["convenient_time"].options],
            ui.CONVENIENT_TIME,
        )
        selects["goals"]._values = [ui.GOALS_LIST[0]]
        await selects["goals"].callback(event)
        self.assertEqual(draft.goals, [ui.GOALS_LIST[0]])
        self.assertEqual(draft.convenient_time, ["Legacy time"])
        self.assertEqual(draft.ranks, {"AION 2": "50"})
        self.assertEqual(
            draft.game_details["AION 2"], {"server": "Siel", "faction": "Элийцы"}
        )
        self.assertFalse(draft.is_active)
        self.assertEqual(player.goals, ["Legacy goal"])

    async def test_my_profile_exposes_options_without_losing_other_fields(self):
        player = profile()
        event = NS(response=NS(edit_message=AsyncMock()))
        await ui.MyProfileView(1, player).options.callback(event)
        kwargs = event.response.edit_message.await_args.kwargs
        draft = kwargs["view"].draft
        self.assertIsInstance(kwargs["view"], ui.ProfileOptionsView)
        self.assertEqual(draft.nickname, player.nickname)
        self.assertEqual(draft.games, ["AION 2"])
        self.assertEqual(draft.goals, player.goals)
        self.assertFalse(draft.is_active)
        self.assertEqual(kwargs["attachments"], [])

    async def test_new_profile_starts_with_standard_selection(self):
        modal = ui.ProfileBasicsModal(1)
        modal.nickname._value = "New"
        modal.age._value = ""
        modal.about._value = "About"
        event = NS(user=NS(id=1))
        with patch.object(ui, "send_temporary", new=AsyncMock()) as send:
            await modal.on_submit(event)
        options = send.await_args.kwargs["view"]
        self.assertIsInstance(options, ui.ProfileOptionsView)
        self.assertEqual(options.draft.goals, [])
        with patch.object(ui, "send_temporary", new=AsyncMock()) as send:
            await options.continue_form.callback(event)
        self.assertIn("Выберите хотя бы одну", send.await_args.args[1])

    async def test_public_entrypoints_allow_profile_creation_and_existing_search(self):
        event = NS(user=NS(id=1))
        panel_view = ui.PublicPanelView()
        with (
            patch.object(
                panel_view, "_profile", new=AsyncMock(return_value=(None, True))
            ),
            patch.object(ui, "send_temporary", new=AsyncMock()) as send,
        ):
            for callback in (panel_view.open_search, panel_view.open_profile):
                await callback(event)
                menu = send.await_args.kwargs["view"]
                self.assertIn("Создать анкету", [item.label for item in menu.children])
        with (
            patch.object(
                panel_view, "_profile", new=AsyncMock(return_value=(profile(), True))
            ),
            patch.object(ui, "send_temporary", new=AsyncMock()) as send,
        ):
            await panel_view.open_search(event)
            self.assertIsInstance(send.await_args.kwargs["view"], ui.SearchModeView)
        legacy = ui.LegacyPublicPanelView()
        self.assertTrue(legacy.is_persistent())
        self.assertEqual(legacy.children[0].custom_id, ui.PublicPanelView.CUSTOM_ID)
        with patch.object(
            ui.PublicPanelView, "open_teamseek", new=AsyncMock()
        ) as open_menu:
            await legacy.children[0].callback(event)
        open_menu.assert_awaited_once_with(event)

    def panel_interaction(self, *, author_id=99, components=None, allowed=True):
        if components is None:
            components = [
                discord.components._component_factory(data)
                for data in ui.PublicPanelView().to_components()
            ]
        message = NS(
            author=NS(id=author_id),
            components=components,
            pinned=True,
            edit=AsyncMock(),
            pin=AsyncMock(),
        )
        event = NS(
            user=NS(id=1, guild_permissions=NS(manage_guild=allowed)),
            client=NS(user=NS(id=99)),
            channel=NS(
                fetch_message=AsyncMock(return_value=message),
                send=AsyncMock(return_value=message),
            ),
            response=NS(defer=AsyncMock()),
        )
        return event, message

    async def test_panel_updates_v2_and_legacy_in_place_without_repinning(self):
        legacy = discord.components._component_factory(
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 1,
                        "custom_id": ui.PublicPanelView.CUSTOM_ID,
                        "label": "Открыть TeamSeek",
                    }
                ],
            }
        )
        for components in (None, [legacy]):
            event, message = self.panel_interaction(components=components)
            with (
                patch(
                    "discord_bot.bot.primary_member", new=AsyncMock(return_value=True)
                ),
                patch("discord_bot.bot.followup_temporary", new=AsyncMock()),
            ):
                await panel.callback(event, "12345")
            event.channel.fetch_message.assert_awaited_once_with(12345)
            message.edit.assert_awaited_once()
            self.assertEqual(message.edit.await_args.kwargs["embeds"], [])
            self.assertIsInstance(
                message.edit.await_args.kwargs["view"], ui.PublicPanelView
            )
            message.pin.assert_not_awaited()
            event.channel.send.assert_not_awaited()

    async def test_panel_rejects_invalid_ids_foreign_messages_and_non_panels(self):
        for message_id, author_id, components in (
            ("bad", 99, None),
            ("0", 99, None),
            ("12345", 88, None),
            ("12345", 99, []),
        ):
            event, message = self.panel_interaction(
                author_id=author_id, components=components
            )
            with (
                patch(
                    "discord_bot.bot.primary_member", new=AsyncMock(return_value=True)
                ),
                patch("discord_bot.bot.followup_temporary", new=AsyncMock()) as reply,
            ):
                await panel.callback(event, message_id)
            message.edit.assert_not_awaited()
            event.channel.send.assert_not_awaited()
            reply.assert_awaited_once()

    async def test_panel_creation_and_permission_check_remain(self):
        event, message = self.panel_interaction()
        with (
            patch("discord_bot.bot.primary_member", new=AsyncMock(return_value=True)),
            patch("discord_bot.bot.followup_temporary", new=AsyncMock()),
        ):
            await panel.callback(event)
        event.channel.send.assert_awaited_once()
        message.pin.assert_awaited_once()
        event, message = self.panel_interaction(allowed=False)
        with patch("discord_bot.bot.send_temporary", new=AsyncMock()) as reply:
            await panel.callback(event, "12345")
        event.channel.fetch_message.assert_not_awaited()
        message.edit.assert_not_awaited()
        reply.assert_awaited_once()
