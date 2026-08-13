from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards.estimate_kb import *
from utils.constants import *
from repositories.profile_repository import profile_repository as repository
from handlers.menu import cmd_menu
from utils.level_up import level_up
from services.platform_repository import platform_repository


router = Router()


class EstimateStates(StatesGroup):
    politeness = State()
    skill = State()
    teamwork = State()


### ТЕКСТЫ
TEXT_RESULT = "Привет! Удалось ли сыграть с {teammate}?"
TEXT_IN_PROCESS = (
    "Окей, держу кулачки! Пожалуйста, оцени {teammate} сразу после совместной игры"
)
TEXT_SUCCESS = "Грац! Оцени пожалуйста своего новоиспеченного друга."
TEXT_FAILED = "Жаль что у вас не получилось. Хочешь продолжить поиск?"
TEXT_POLITENESS = "Насколько вежливым был {teammate}?"
TEXT_SKILL = "Оцени скилл {teammate}"
TEXT_TEAMWORK = "На сколько {teammate} проявил себя в командной игре?"
TEXT_THANKS = (
    "Спасибо за оценку! Твой отзыв поможет улучшить качество подбора тиммейтов."
)


async def ask_connect(
    bot: Bot, user_id: int, teammate: str, teammate_id: int, state: FSMContext
):
    await state.update_data(teammate=teammate, teammate_id=teammate_id)
    await bot.send_message(
        chat_id=user_id,
        text=TEXT_RESULT.format(teammate=teammate),
        reply_markup=await get_connect_kb(),
    )


@router.callback_query(F.data.in_(["in_process", "success", "fail"]))
async def handle_connect_answer(callback: CallbackQuery, state: FSMContext):
    answer = callback.data

    await callback.message.delete()

    await callback.answer()

    # Сохраняем имя тиммейта в состоянии (предполагается, что оно передается откуда-то)
    data = await state.get_data()
    teammate = data.get("teammate", "тиммейт")

    if answer == "success":
        await callback.message.answer(TEXT_SUCCESS, reply_markup=ReplyKeyboardRemove())

        await callback.message.answer(
            TEXT_POLITENESS.format(teammate=teammate),
            reply_markup=await get_scale_kb("politeness"),
        )
        await state.set_state(EstimateStates.politeness)

    elif answer == "in_process":
        await callback.message.answer(
            TEXT_IN_PROCESS.format(teammate=teammate),
            reply_markup=await get_success_kb(),
        )

    elif answer == "fail":
        await callback.message.answer(TEXT_FAILED, reply_markup=await get_search_kb())
        await state.clear()


@router.callback_query(F.data == "estimate_callback")
async def handle_success_after_process(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    data = await state.get_data()
    teammate = data.get("teammate", "тиммейт")

    await callback.message.answer(TEXT_SUCCESS, reply_markup=ReplyKeyboardRemove())

    await callback.message.answer(
        TEXT_POLITENESS.format(teammate=teammate),
        reply_markup=await get_scale_kb("politeness"),
    )

    await callback.answer()
    await state.set_state(EstimateStates.politeness)


@router.callback_query(F.data.startswith("estimate_politeness_"))
async def handle_politeness_rating(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[-1])  # Конвертируем в int
    data = await state.get_data()
    teammate = data.get("teammate", "тиммейт")

    await state.update_data(politeness_rating=rating)

    await callback.message.edit_text(
        f"Вежливость: {rating}⭐\n\n{TEXT_SKILL.format(teammate=teammate)}",
        reply_markup=await get_scale_kb("skill"),
    )
    await state.set_state(EstimateStates.skill)
    await callback.answer()


@router.callback_query(F.data.startswith("estimate_skill_"))
async def handle_skill_rating(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[-1])  # Конвертируем в int
    data = await state.get_data()
    teammate = data.get("teammate", "тиммейт")
    politeness_rating = data.get("politeness_rating", 0)

    await state.update_data(skill_rating=rating)

    await callback.message.edit_text(
        f"Вежливость: {politeness_rating}⭐\nСкилл: {rating}⭐\n\n{TEXT_TEAMWORK.format(teammate=teammate)}",
        reply_markup=await get_scale_kb("teamwork"),
    )
    await state.set_state(EstimateStates.teamwork)
    await callback.answer()


@router.callback_query(F.data.startswith("estimate_teamwork_"))
async def handle_teamwork_rating(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[-1])  # Конвертируем в int
    data = await state.get_data()
    politeness_rating = data.get("politeness_rating", 0)
    skill_rating = data.get("skill_rating", 0)

    if "teammate_id" in data:
        teammate_id = data["teammate_id"]
    else:
        await callback.message.answer(
            "Я потерял id твоего тиммейта. Попробуй заново пригласить твоего тиммейта в игру и потом оцени его"
        )

    await callback.message.edit_text(
        f"Вежливость: {politeness_rating}⭐\nСкилл: {skill_rating}⭐\nКомандная игра: {rating}⭐"  # Исправлена опечатка
    )

    reviewer = await platform_repository.get_profile("telegram", callback.from_user.id)
    target = await platform_repository.get_profile("telegram", teammate_id)
    if not reviewer or not target:
        await callback.answer("Анкета тиммейта не найдена", show_alert=True)
        return
    is_new = await platform_repository.upsert_review(
        reviewer_profile_id=reviewer.id,
        target_profile_id=target.id,
        contact_request_id=None,
        polite=politeness_rating,
        skill=skill_rating,
        team_game=rating,
    )

    await callback.message.answer("Оценка сохранена!")

    if is_new:
        awarded, _, new_level = await platform_repository.award_rating_experience(
            reviewer.id, target.id
        )
        if awarded and new_level > (reviewer.experience or 0) // 100 + 1:
            await level_up(callback.bot, user_id=reviewer.user_id, new_level=new_level)

    await state.clear()
    await callback.answer()

    await cmd_menu(callback.message)
