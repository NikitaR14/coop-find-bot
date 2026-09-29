import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
import tests.test_smoke  # noqa: F401 -- isolated settings
from discord_bot import messages, ui


class Clock:
    def __init__(self):
        self.now = 0
        self.waiters = []

    async def sleep(self, delay):
        future = asyncio.get_running_loop().create_future()
        self.waiters.append((self.now + delay, future))
        await future

    async def advance(self, seconds):
        # Let newly scheduled expiry tasks register before advancing time.
        await asyncio.sleep(0)
        self.now += seconds
        for deadline, future in self.waiters:
            if deadline <= self.now and not future.done():
                future.set_result(None)
        await asyncio.sleep(0)


def interaction(message_id=10, *, private=True, user_id=1):
    message = NS(
        id=message_id, flags=discord.MessageFlags(ephemeral=private), delete=AsyncMock()
    )
    return NS(
        user=NS(id=user_id),
        message=message,
        response=NS(
            send_message=AsyncMock(return_value=NS(message_id=message_id)),
            edit_message=AsyncMock(),
            defer=AsyncMock(),
            send_modal=AsyncMock(),
        ),
        followup=NS(send=AsyncMock(return_value=message), delete_message=AsyncMock()),
        delete_original_response=AsyncMock(),
        original_response=AsyncMock(return_value=message),
    )


class IdleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = Clock()
        self.manager = messages.TemporaryMessages(sleep=self.clock.sleep)
        self.patcher = patch.object(messages, "temporary_messages", self.manager)
        self.patcher.start()

    async def asyncTearDown(self):
        await self.manager.close()
        self.patcher.stop()

    async def test_initial_response_expires_at_180_seconds(self):
        event = interaction()
        await messages.send_temporary(event, "Private", ephemeral=True)
        self.assertNotIn("delete_after", event.response.send_message.await_args.kwargs)
        await self.clock.advance(179)
        event.delete_original_response.assert_not_awaited()
        await self.clock.advance(1)
        event.delete_original_response.assert_awaited_once_with()
        self.assertFalse(self.manager._tasks)

    async def test_activity_cancels_old_timer_and_uses_fresh_webhook(self):
        original = interaction()
        fresh = interaction()
        await messages.send_temporary(original, "Private", ephemeral=True)
        await self.clock.advance(170)
        self.assertTrue(await ui.OwnedView(1).interaction_check(fresh))
        await self.clock.advance(10)
        original.delete_original_response.assert_not_awaited()
        fresh.followup.delete_message.assert_not_awaited()
        await self.clock.advance(170)
        fresh.followup.delete_message.assert_awaited_once_with(10)
        self.assertFalse(self.manager._tasks)

    async def test_long_session_keeps_using_latest_interaction_token(self):
        original = interaction()
        await messages.send_temporary(original, "Private", ephemeral=True)
        events = []
        for _ in range(10):
            await self.clock.advance(170)
            event = interaction()
            messages.touch_temporary(event)
            events.append(event)
        await self.clock.advance(180)
        original.delete_original_response.assert_not_awaited()
        for event in events[:-1]:
            event.followup.delete_message.assert_not_awaited()
        events[-1].followup.delete_message.assert_awaited_once_with(10)

    async def test_edits_renew_and_messages_expire_independently(self):
        first = interaction(10)
        second = interaction(20, user_id=2)
        await messages.send_temporary(first, "One", ephemeral=True)
        await messages.send_temporary(second, "Two", ephemeral=True)
        await self.clock.advance(100)
        await messages.edit_temporary(first, content="Updated")
        await self.clock.advance(80)
        second.delete_original_response.assert_awaited_once()
        first.delete_original_response.assert_not_awaited()
        await self.clock.advance(100)
        first.followup.delete_message.assert_awaited_once_with(10)

    async def test_followup_after_private_defer_inherits_privacy(self):
        event = interaction()
        await event.response.defer(ephemeral=True, thinking=True)
        await messages.followup_temporary(event, "Done")
        self.assertTrue(event.followup.send.await_args.kwargs["wait"])
        event.message.delete.assert_not_awaited()
        await self.clock.advance(180)
        event.message.delete.assert_awaited_once_with()

    async def test_public_panels_and_dm_buttons_never_expire(self):
        event = interaction(private=False)
        await messages.send_temporary(event, "Public")
        await messages.followup_temporary(event, "Public followup")
        await ui.OwnedView(1).interaction_check(event)
        await messages.edit_temporary(event, content="DM updated")
        await ui.TemporaryModal(title="DM").interaction_check(event)
        self.assertFalse(self.manager._tasks)

    async def test_unauthorised_click_does_not_extend_source(self):
        original = interaction()
        await messages.send_temporary(original, "Private", ephemeral=True)
        await self.clock.advance(100)
        wrong_user = interaction(user_id=2)
        wrong_user.response.send_message.return_value.message_id = 20
        self.assertFalse(await ui.OwnedLayoutView(1).interaction_check(wrong_user))
        await self.clock.advance(80)
        original.delete_original_response.assert_awaited_once()
        wrong_user.followup.delete_message.assert_not_awaited()
        wrong_user.delete_original_response.assert_not_awaited()

    async def test_select_defer_modal_open_and_submit_refresh_idle(self):
        draft = ui.ProfileDraft("Player", None, "About")
        view = ui.ProfileOptionsView(1, draft)
        event = interaction()
        await messages.send_temporary(event, view=view, ephemeral=True)
        await self.clock.advance(170)
        await view.interaction_check(event)
        select = next(
            item for item in view.children if isinstance(item, ui.DraftSelect)
        )
        select._values = [ui.GENDER_LIST[0]]
        await select.callback(event)
        event.response.defer.assert_awaited_once()
        await self.clock.advance(170)
        confirm = ui.ProfileConfirmView(1, draft)
        await confirm.interaction_check(event)
        await confirm.edit.callback(event)
        modal = event.response.send_modal.await_args.args[0]
        await self.clock.advance(170)
        submission = interaction()
        await modal.interaction_check(submission)
        for item in modal.children:
            item._value = item.default or ""
        with patch.object(ui, "send_profile_preview", new=AsyncMock()):
            await modal.on_submit(submission)
        await self.clock.advance(179)
        event.followup.delete_message.assert_not_awaited()
        await self.clock.advance(1)
        submission.followup.delete_message.assert_awaited_once_with(10)

    async def test_expired_source_does_not_discard_modal_draft(self):
        event = interaction()
        draft = ui.ProfileDraft("Player", None, "About", goals=["Legacy"])
        modal = ui.ProfileBasicsModal(1, draft=draft)
        await messages.send_temporary(event, "Preview", ephemeral=True)
        await self.clock.advance(180)
        submission = interaction()
        await modal.interaction_check(submission)
        for item in modal.children:
            item._value = item.default or ""
        with patch.object(ui, "send_profile_preview", new=AsyncMock()) as preview:
            await modal.on_submit(submission)
        preview.assert_awaited_once_with(submission, draft)
        self.assertEqual(draft.goals, ["Legacy"])

    async def test_deleted_message_errors_and_shutdown_cleanup(self):
        response = NS(status=404, reason="Not Found")
        gone = AsyncMock(side_effect=discord.NotFound(response, "gone"))
        self.manager.renew(10, gone)
        await self.clock.advance(180)
        self.assertFalse(self.manager._tasks)
        forbidden = AsyncMock(
            side_effect=discord.Forbidden(NS(status=403, reason="Forbidden"), "denied")
        )
        self.manager.renew(20, forbidden)
        with self.assertLogs("discord_bot.messages", level="WARNING"):
            await self.clock.advance(180)
        self.assertFalse(self.manager._tasks)
        self.manager.renew(25, AsyncMock(side_effect=OSError("network unavailable")))
        with self.assertLogs("discord_bot.messages", level="WARNING"):
            await self.clock.advance(180)
        self.assertFalse(self.manager._tasks)
        pending = AsyncMock()
        self.manager.renew(30, pending)
        await self.manager.close()
        await self.clock.advance(180)
        pending.assert_not_awaited()
        self.assertFalse(self.manager._tasks)
