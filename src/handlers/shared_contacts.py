from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from services.delivery import deliver_text
from services.platform_repository import platform_repository


router = Router()


def score_keyboard(prefix: str, request_id: int, *scores: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{score}⭐",
                    callback_data=f"{prefix}:{request_id}:{score}:"
                    + ":".join(map(str, scores)),
                )
                for score in range(1, 6)
            ]
        ]
    )


@router.message(Command("reply"))
async def reply_to_contact(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Формат ответа: <code>/reply номер текст</code>")
        return
    request_id = int(parts[1])
    current = await platform_repository.get_profile("telegram", message.from_user.id)
    request = await platform_repository.get_contact_request(request_id)
    if not current or not request or request.target_profile_id != current.id:
        await message.answer(
            "Сообщение не найдено или принадлежит другому пользователю."
        )
        return
    sender = await platform_repository.get_profile_by_id(request.sender_profile_id)
    if not sender:
        await message.answer("Анкета отправителя уже удалена.")
        return
    result = await deliver_text(sender, f"↩️ Ответ от {current.nickname}\n\n{parts[2]}")
    await message.answer(
        "Ответ отправлен." if result.delivered else "Не удалось доставить ответ."
    )


@router.message(Command("rate"))
async def start_shared_rating(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат оценки: <code>/rate номер</code>")
        return
    request_id = int(parts[1])
    current = await platform_repository.get_profile("telegram", message.from_user.id)
    request = await platform_repository.get_contact_request(request_id)
    if not current or not request or request.sender_profile_id != current.id:
        await message.answer(
            "Приглашение не найдено или принадлежит другому пользователю."
        )
        return
    target = await platform_repository.get_profile_by_id(request.target_profile_id)
    if not target:
        await message.answer("Анкета тиммейта уже удалена.")
        return
    await message.answer(
        f"Насколько вежливым был {target.nickname}?",
        reply_markup=score_keyboard("srp", request_id),
    )


@router.callback_query(F.data.startswith("rating_result:"))
async def rating_result(callback: CallbackQuery) -> None:
    _, request_value, action = callback.data.split(":")
    request_id = int(request_value)
    current = await platform_repository.get_profile("telegram", callback.from_user.id)
    request = await platform_repository.get_contact_request(request_id)
    if not current or not request or request.sender_profile_id != current.id:
        await callback.answer("Приглашение не найдено", show_alert=True)
        return
    if action == "yes":
        target = await platform_repository.get_profile_by_id(request.target_profile_id)
        if not target:
            await callback.answer("Анкета игрока удалена", show_alert=True)
            return
        await callback.message.edit_text(
            f"Насколько вежливым был {target.nickname}?",
            reply_markup=score_keyboard("srp", request_id),
        )
    elif action == "waiting":
        await platform_repository.set_contact_status(request_id, "in_process")
        await callback.message.edit_text(
            f"Хорошо, вернёмся к вопросу позже. Оценить можно командой /rate {request_id}."
        )
    else:
        await platform_repository.set_contact_status(request_id, "declined")
        await callback.message.edit_text("Понял. Оценка не требуется.")
    await callback.answer()


@router.callback_query(F.data.startswith("srp:"))
async def shared_rating_polite(callback: CallbackQuery) -> None:
    _, request_id, polite, _ = callback.data.split(":", 3)
    await callback.message.edit_text(
        f"Вежливость: {polite}⭐\n\nОцените игровой навык:",
        reply_markup=score_keyboard("srs", int(request_id), int(polite)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("srs:"))
async def shared_rating_skill(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    request_id, skill, polite = map(int, parts[1:4])
    await callback.message.edit_text(
        f"Вежливость: {polite}⭐\nНавык: {skill}⭐\n\nОцените командную игру:",
        reply_markup=score_keyboard("srt", request_id, polite, skill),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("srt:"))
async def shared_rating_team(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    request_id, team_game, polite, skill = map(int, parts[1:5])
    current = await platform_repository.get_profile("telegram", callback.from_user.id)
    request = await platform_repository.get_contact_request(request_id)
    if not current or not request or request.sender_profile_id != current.id:
        await callback.answer("Приглашение не найдено", show_alert=True)
        return
    is_new = await platform_repository.upsert_review(
        reviewer_profile_id=current.id,
        target_profile_id=request.target_profile_id,
        contact_request_id=request.id,
        polite=polite,
        skill=skill,
        team_game=team_game,
    )
    xp_text = ""
    if is_new:
        (
            awarded,
            old_level,
            new_level,
        ) = await platform_repository.award_rating_experience(
            current.id, request.target_profile_id
        )
        if awarded:
            xp_text = "\nНачислено 10 опыта."
            if new_level > old_level:
                xp_text += f" Новый уровень: {new_level} ⚡"
    await platform_repository.set_contact_status(request.id, "completed")
    await callback.message.edit_text(
        f"Вежливость: {polite}⭐\nНавык: {skill}⭐\nКомандная игра: {team_game}⭐\n\nОценка сохранена. Спасибо!{xp_text}"
    )
    await callback.answer()


@router.message(Command("accept"))
async def accept_clan_application(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат принятия заявки: <code>/accept номер</code>")
        return
    current = await platform_repository.get_profile("telegram", message.from_user.id)
    if not current:
        await message.answer("Сначала создайте анкету.")
        return
    applicant, awarded = await platform_repository.accept_clan_application(
        int(parts[1]), current.id
    )
    if not applicant:
        await message.answer("Заявка не найдена или уже закрыта.")
        return
    if awarded:
        await deliver_text(
            applicant,
            f"🏰 {current.nickname} принял вашу заявку в клан. Начислено 30 опыта.",
        )
    await message.answer(
        "Заявка принята." if awarded else "Эта заявка уже была принята."
    )
