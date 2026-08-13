from aiogram import Bot, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from utils.creation_process import render_clan_info
from utils.constants import *
from utils.schedule_estimate import schedule_estimate
from keyboards.search_kb import *
from repositories.profile_repository import profile_repository as repository
from services.delivery import accept_instruction, deliver_text, reply_instruction
from services.platform_repository import platform_repository
from repositories.clan_repository import clan_repository
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from utils.level_up import level_up
from states.search import *
from utils.ranks import *
from keyboards.profile_kb import (
    get_ranks_kb,
    get_standoff_ranks,
    get_warcraft_modes_kb,
    get_warcraft_ranks_kb,
    get_raven_clusters_kb,
    get_lineage_servers_pt_1,
    get_marvel_ranks,
)
from handlers.profile.create_profile import TEXT_WARCRAFT_MODE, handle_ranks_pagination
from statistic import Statistic
import asyncio
from utils.profile_templates import get_raven2_rank_template
from utils.profile_templates import get_warcraft_rank_template
from html import escape
from utils.decorators import require_profile


router = Router()

### НОВЫЕ ТЕКСТЫ
TEXT_CHOOSE_SEARCH_TYPE = """
Ну что, готов найти себе идеальную компанию? Выбери, кого будем искать: одного игрока или целый клан👇
"""
TEXT_CHOOSE_GAME_FOR_CLAN = "Выбирай игру, по которой ищешь клан👇"
TEXT_NO_CLANS = """
Похоже, активных кланов по {game} сейчас нет 🤷‍♂️

Но не расстраивайся, ведь кто-то же должен быть первым. Предлагаю создать свой клан, заполнить анкету и ждать заявок в свой клан. А еще свой клан — это свои правила ☝️
"""
TEXT_CLANS_FOUND = """
🔥 Опа, нашел пару кланов!

Да, список маленький… но размер — не главное 😏
Загляни, вдруг именно там тебя уже ждут с тёплым «го в катку?».

"""
TEXT_JOIN_CLAN = "Отправить заявку на вступление в клан"
TEXT_INTRO = "Выбери игру."
TEXT_WRONG_NAME_GANE = "Выбери игру из предложенного списка"
TEXT_ANSWER_TYPE_ERROR = "Ответь текстом."
TEXT_NO_PROFILES = """
По {game} пока пустовато — активных анкет не нашлось😕

Хочешь стать первопроходцем и получать приглашения первым? Заполни свою анкету и жди приглашений от тех, кто будет искать тиммейта позже.
"""
TEXT_PROFILES_FOUND = """
Вот список тех, кто готов играть прямо сейчас 🔥
Выбери того, кто тебе подходит, и отправь ему приглашение👇
"""
TEXT_SEND_MESSAGE = "Напиши пару ласковых этому фрукту"
TEXT_TRIED_TO_SEND_MESSAGE = (
    "Бот попытался отправить сообщение, но что-то пошло не так..."
)
TEXT_SENT_MESSAGE = "Сообщение отправил. Ответ прилетит в личные сообщения."
TEXT_MESSAGE = "Пользователь {name} отправил тебе сообщение:\n\n{message}"
TEXT_ADDITIONAL_INFO = "\nЕго тег в телеграме - {tag}"
TEXT_INVITE = "Пользователь {name} приглашает тебя в {game}."
TEXT_RSL = """
Введи силу аккаунта в миллионах 🌟
Если сила меньше 1 млн — впиши дробное значение.

Пример: 500 000 тыс = 0,5 млн
"""
TEXT_NUM_RANK = "Введи силу аккаунта числом:"
TEXT_PROFILES_SEARCH_TYPE = """
Выбери режим поиска:
Можешь начать поиск анкеты по критериям или просто открыть все доступные объявления. 👇
"""
TEXT_GAMES = """
Настало время найти того самого тиммейта⚔️

Выбери игру и я покажу объявления тех, кто также сейчас ищет с кем бы поиграть👇
"""

TEXT_EMOJI = """
Рядом с каждым ником стоит оценка на основе прошлых игр. Расшифровка эмодзи:
Вежливость — 🌸
Навык — 🎮
Командная игра — 🤝
Уровень — ⭐️

Рядом с ником стоит только показатель уровня ⭐️, значит пользователя еще не оценили и ты можешь стать первым!
"""

MESSAGE_TEXT = """
Пользователь {nick} заинтересовался твоей анкетой по {game} и отправил тебе сообщение:

{text}
"""

TEXT_BEFORE_INVITE_CLAN = """
Перед отправкой заявки напиши пару слов для главы клана ✍
  
Расскажи о себе, опыте или почему хочешь вступить. Это увеличит шанс попасть в клан
"""


@router.message(Command("search"))
async def start_search(message: Message, state: FSMContext):
    await message.delete()
    await state.set_state(GameForm.search_type)
    await message.answer(
        text=TEXT_CHOOSE_SEARCH_TYPE, reply_markup=await get_search_type_kb()
    )


@router.callback_query(F.data == "start_search")
async def start_search_callback(
    callback: CallbackQuery, state: FSMContext, statistic: Statistic
):
    asyncio.create_task(statistic.set_start_search(callback.from_user.id))
    await callback.message.delete()
    await state.set_state(GameForm.search_type)
    await callback.message.answer(
        text=TEXT_CHOOSE_SEARCH_TYPE, reply_markup=await get_search_type_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("search_type_"))
async def choose_search_type(callback: CallbackQuery, state: FSMContext):
    search_type = callback.data.split("_")[-1]
    await callback.answer()

    await callback.message.delete()

    await state.update_data(search_type=search_type)
    if search_type != "profiles":
        await state.set_state(GameForm.game)

        await callback.message.answer(
            text=TEXT_CHOOSE_GAME_FOR_CLAN, reply_markup=await get_game_inline_kb()
        )
    else:
        await callback.message.answer(
            TEXT_PROFILES_SEARCH_TYPE, reply_markup=await get_search_profiles_types()
        )


@router.callback_query(F.data == "game_search")
async def game_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await callback.message.delete()

    await state.set_state(GameForm.game)

    await callback.message.answer(
        text=TEXT_GAMES, reply_markup=await get_game_inline_kb()
    )


@router.callback_query(F.data.startswith("get_profiles_by_"))
async def get_profiles_callback_handler(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()

    game = callback.data.split("_")[-1]
    data = await state.get_data()
    search_type = data.get("search_type", "profiles")

    await callback.answer()

    if search_type == "profiles":
        await get_profiles_by_game_callback(callback, state, game)
    elif search_type == "clans":
        await get_clans_by_game_callback(callback, state, game)


async def get_profiles_by_game_callback(
    callback: CallbackQuery, state: FSMContext, game: str
):
    profiles = await repository.get_profiles_by_game(
        game=game, user_id=callback.from_user.id
    )
    # await callback.message.delete()

    if profiles:
        await state.clear()
        await state.update_data(
            profiles=profiles, current_page=0, game=game, search_type="profiles"
        )

        keyboard = await get_profiles_kb(profiles, game=game, page=0)
        await callback.message.edit_text(
            text=TEXT_PROFILES_FOUND,
        )
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    else:
        await callback.message.edit_text(text=TEXT_NO_PROFILES.format(game=game))
        await callback.message.edit_reply_markup(
            reply_markup=await get_back_to_games_kb("profiles")
        )
        await state.clear()


async def get_clans_by_game_callback(
    callback: CallbackQuery, state: FSMContext, game: str
):
    if game == "AION 2":
        await state.update_data(game=game, search_type="clans")
        await callback.message.edit_text(
            "Введите сервер AION 2 для поиска клана или напишите «Пропустить»:"
        )
        await state.set_state(ClanFilterForm.server)
        return
    clans = await clan_repository.get_clans_by_game(
        game=game, user_id=callback.from_user.id
    )
    # await callback.message.delete()

    if clans:
        await state.clear()
        await state.update_data(
            clans=clans, current_page=0, game=game, search_type="clans"
        )

        keyboard = await get_clans_kb(clans, page=0)
        await callback.message.edit_text(text=TEXT_CLANS_FOUND)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    else:
        await callback.message.edit_text(text=TEXT_NO_CLANS.format(game=game))
        await callback.message.edit_reply_markup(
            reply_markup=await get_back_to_games_kb("clans")
        )
        await state.clear()


@router.message(ClanFilterForm.server)
async def filter_aion_clan_server(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введите сервер или напишите «Пропустить»:")
        return
    server = (
        None if message.text.strip().lower() == "пропустить" else message.text.strip()
    )
    await state.update_data(clan_server=server)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Любая", callback_data="clan_aion_faction_skip"
                )
            ],
            *[
                [
                    InlineKeyboardButton(
                        text=value, callback_data=f"clan_aion_faction_{value}"
                    )
                ]
                for value in AION_2_FACTIONS
            ],
        ]
    )
    await message.answer("Выберите фракцию:", reply_markup=markup)
    await state.set_state(ClanFilterForm.faction)


@router.callback_query(ClanFilterForm.faction, F.data.startswith("clan_aion_faction_"))
async def filter_aion_clan_faction(callback: CallbackQuery, state: FSMContext):
    value = callback.data.removeprefix("clan_aion_faction_")
    faction = None if value == "skip" else value
    data = await state.get_data()
    clans = await clan_repository.get_clans_by_game(
        game="AION 2",
        user_id=callback.from_user.id,
        server=data.get("clan_server"),
        faction=faction,
    )
    if clans:
        await state.update_data(
            clans=clans, current_page=0, game="AION 2", search_type="clans"
        )
        await callback.message.edit_text(
            TEXT_CLANS_FOUND, reply_markup=await get_clans_kb(clans, page=0)
        )
    else:
        await callback.message.edit_text(
            TEXT_NO_CLANS.format(game="AION 2"),
            reply_markup=await get_back_to_games_kb("clans"),
        )
        await state.clear()
    await callback.answer()


# Хендлеры для профилей
@router.callback_query(F.data.startswith("profiles_page_"))
async def handle_profiles_pagination(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()

    page = int(callback.data.split("_")[-1])
    data = await state.get_data()
    profiles = data.get("profiles", [])
    game = data["game"]

    if profiles:
        await state.update_data(current_page=page)
        keyboard = await get_profiles_kb(profiles, game=game, page=page)
        await callback.message.edit_reply_markup(reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("send_message_to_user_"))
@router.callback_query(F.data.startswith("send_message_to_profile_"))
@require_profile
async def send_message(
    callback: CallbackQuery, state: FSMContext, statistic: Statistic
):
    asyncio.create_task(statistic.set_invite_game(callback.from_user.id))
    await callback.answer()

    reference_id = int(callback.data.split("_")[-1])
    if callback.data.startswith("send_message_to_profile_"):
        target_profile = await platform_repository.get_profile_by_id(reference_id)
    else:
        target_profile = await platform_repository.get_profile("telegram", reference_id)
    if not target_profile:
        await callback.message.answer(
            "Анкета больше недоступна.", reply_markup=await get_back_kb()
        )
        return

    data = await state.get_data()
    game = data.get("game")

    await state.set_state(SendMessageForm.message)
    await state.update_data(target_profile_id=target_profile.id, game=game)

    await callback.message.answer(
        text=TEXT_SEND_MESSAGE, reply_markup=await get_back_kb()
    )


@router.message(SendMessageForm.message)
@require_profile
async def send_message_to_user(message: Message, state: FSMContext):
    if message.text:
        data = await state.get_data()
        target_profile_id = data.get("target_profile_id")
        game = data.get("game")

        if not target_profile_id or not game:
            await message.answer(text="Произошла ошибка. Попробуйте заново.")
            await state.clear()
            return

        profile = await platform_repository.get_profile(
            "telegram", message.from_user.id
        )
        target_profile = await platform_repository.get_profile_by_id(target_profile_id)
        if not profile or not target_profile:
            await message.answer(
                text="Анкета больше недоступна.", reply_markup=await get_back_kb()
            )
            await state.clear()
            return
        try:
            contact = await platform_repository.create_contact_request(
                sender_profile_id=profile.id,
                target_profile_id=target_profile.id,
                kind="message",
                game=game,
                message=message.text,
            )
            result = await deliver_text(
                target_profile,
                MESSAGE_TEXT.format(nick=profile.nickname, game=game, text=message.text)
                + f"\n\nОтветить: {reply_instruction(target_profile, contact.id)}",
            )
            if not result.delivered:
                await platform_repository.mark_contact_failed(contact.id)
                raise RuntimeError(result.reason or "delivery failed")
            await message.answer(
                text=TEXT_SENT_MESSAGE, reply_markup=await get_back_kb()
            )
            awarded, _, new_level = await platform_repository.award_first_message(
                profile.id
            )
            if awarded and new_level > (profile.experience or 0) // 100 + 1:
                await level_up(message.bot, profile.user_id, new_level)
        except Exception as e:
            await message.answer(
                text=TEXT_TRIED_TO_SEND_MESSAGE, reply_markup=await get_back_kb()
            )
            print(e)

        # Очищаем состояние, но сохраняем игру для возможности вернуться
        await state.clear()
        await state.update_data(game=game, search_type="profiles")
    else:
        await message.answer(text=TEXT_ANSWER_TYPE_ERROR)
        await state.set_state(SendMessageForm.message)


@router.callback_query(F.data.startswith("message_without_game_"))
@require_profile
async def message_without_game(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split("_")[-1])

    await state.set_state(SendMessageForm.message_without_game)
    await state.update_data(user_id=user_id)

    await callback.message.answer(text=TEXT_SEND_MESSAGE)


@router.message(SendMessageForm.message_without_game)
async def controller_message_without_game(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id", None)

    if not user_id:
        await message.answer(text="Произошла ошибка. Попробуйте заново.")
        await state.clear()
        return

    if message.text:
        try:
            if message.from_user.username:
                user = "@" + message.from_user.username
            else:
                user = (await repository.get_profile(user_id=user_id)).nickname

            await message.bot.send_message(
                chat_id=user_id,
                text=f"Пользователь {user} отправил тебе сообщение:\n\n{message.text}",
                reply_markup=await get_to_dialog_with_user_kb(
                    user_id=message.from_user.id
                ),
            )
            await message.answer(text=TEXT_SENT_MESSAGE)
        except Exception as e:
            print(e)
            await message.answer(text=TEXT_TRIED_TO_SEND_MESSAGE)

    await state.clear()


@router.callback_query(F.data.startswith("invite_user_"))
@router.callback_query(F.data.startswith("invite_profile_"))
@require_profile
async def invite_user(
    callback: CallbackQuery,
    state: FSMContext,
    apscheduler: AsyncIOScheduler,
    statistic: Statistic,
):
    asyncio.create_task(statistic.set_invite_game(callback.from_user.id))
    callback_parts = callback.data.split("_")
    reference_id = int(callback_parts[-1])
    game = callback_parts[-2]
    profile = (
        await platform_repository.get_profile_by_id(reference_id)
        if callback.data.startswith("invite_profile_")
        else await platform_repository.get_profile("telegram", reference_id)
    )
    user_profile = await platform_repository.get_profile(
        "telegram", callback.from_user.id
    )

    if not profile:
        await callback.answer("Профиль не найден")
        return

    await state.update_data(game=game, search_type="profiles")

    try:
        contact = await platform_repository.create_contact_request(
            sender_profile_id=user_profile.id,
            target_profile_id=profile.id,
            kind="invite",
            game=game,
            message=None,
        )
        result = await deliver_text(
            profile,
            TEXT_INVITE.format(name=user_profile.nickname, game=game)
            + f"\n\nОтветить: {reply_instruction(profile, contact.id)}",
        )
        if not result.delivered:
            await platform_repository.mark_contact_failed(contact.id)
            raise RuntimeError(result.reason or "delivery failed")
        await callback.message.answer(
            text=TEXT_SENT_MESSAGE, reply_markup=await get_back_kb()
        )
    except Exception as e:
        await callback.message.answer(
            text=TEXT_TRIED_TO_SEND_MESSAGE, reply_markup=await get_back_kb()
        )
        print(e)

    await callback.answer()


# Хендлеры для кланов
@router.callback_query(F.data.startswith("clans_page_"))
async def handle_clans_pagination(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()

    page = int(callback.data.split("_")[-1])
    data = await state.get_data()
    clans = data.get("clans", [])

    if clans:
        await state.update_data(current_page=page)
        keyboard = await get_clans_kb(clans, page=page)
        await callback.message.edit_reply_markup(reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("view_clan_"))
async def view_clan_detail(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()
    data = await state.get_data()

    try:
        clan_id = int(callback.data.split("_")[-1])
    except:
        clan_id = data["clan_id"]

    clans = data.get("clans", [])
    game = data.get("game")

    clan = next((c for c in clans if c.id == clan_id), None)

    if not clan:
        await callback.answer("Клан не найден")
        return

    clan_info = f"<b>Название клана</b>: {escape(clan.name)}\n\n"
    clan_info += f"<b>Игра</b>: {escape(clan.game)}\n\n"
    clan_info += f"<b>Платформа</b>: {'Discord' if clan.platform == 'discord' else 'Telegram'}\n\n"
    if clan.server:
        clan_info += f"<b>Сервер</b>: {escape(clan.server)}\n\n"
    if clan.faction:
        clan_info += f"<b>Фракция</b>: {escape(clan.faction)}\n\n"
    if clan.add_info:
        add_info = await render_clan_info(clan.game, clan.add_info)
        clan_info += f"<b>Дополнительная информация</b>:\n{add_info}\n\n"
    clan_info += f"<b>Описание</b>: {escape(clan.description)}\n\n"
    clan_info += f"<b>Требования</b>: {escape(clan.demands)}\n\n"

    from aiogram.exceptions import TelegramBadRequest

    try:
        if clan.platform != "telegram":
            raise LookupError
        user = await callback.bot.get_chat(clan.user_id)
        if user.username:
            clan_info += f"<b>Тег лидера клана</b>: @{escape(user.username)}\n\n"

    except TelegramBadRequest:
        user = await repository.get_profile(user_id=clan.user_id)
        if user.nickname:
            clan_info += f"<b>Тег лидера клана</b>: @{escape(user.nickname)}\n\n"
    except Exception:
        leader = await platform_repository.get_profile(clan.platform, clan.user_id)
        if leader:
            clan_info += f"<b>Лидер клана</b>: {escape(leader.nickname)}\n\n"

    if clan.created_at:
        time = clan.created_at.strftime("%d.%m.%Y %H:%M")
        clan_info += f"<b>Дата размещения</b>: {time}"

    await callback.answer()

    await callback.message.answer(
        text=clan_info, reply_markup=await get_clan_detail_kb(clan_id, game)
    )


@router.callback_query(F.data.startswith("join_clan_"))
async def send_msg_before_join(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    clan_id = int(callback.data.split("_")[-1])
    await state.update_data(clan_id=clan_id, user_id=callback.from_user.id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить⏩", callback_data="skip_send_msg_before_join"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назад⬅", callback_data="back_send_msg_before_join"
                )
            ],
        ]
    )

    await callback.message.answer(text=TEXT_BEFORE_INVITE_CLAN, reply_markup=keyboard)
    await state.set_state(ClanForm.message)


@router.callback_query(
    F.data.in_(["skip_send_msg_before_join", "back_send_msg_before_join"])
)
async def select_action_before_invite_clan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()

    await state.set_state(None)

    if callback.data == "skip_send_msg_before_join":
        await join_clan_v2(callback.bot, state)
    elif callback.data == "back_send_msg_before_join":
        await view_clan_detail(callback, state)

    return


@router.message(ClanForm.message)
async def handle_mesg_before_join_clan(message: Message, state: FSMContext):
    if message.text:
        await state.update_data(msg_before_join=message.text)

    await join_clan_v2(message.bot, state)


async def join_clan_v2(bot: Bot, state: FSMContext):
    data = await state.get_data()
    user_id = data["user_id"]

    msg_before_join = data.get("msg_before_join", None)

    try:
        clan_id = data["clan_id"]

        clans = data.get("clans", [])

        clan = next((c for c in clans if c.id == clan_id), None)
        if not clan:
            await bot.send_message(chat_id=user_id, text="Клан не найден")
            return

        await state.update_data(game=clan.game)

        user_profile = await platform_repository.get_profile("telegram", user_id)
        username = user_profile.nickname

        join_message = f"🏰 Заявка на вступление в клан {escape(clan.name)}\n\n"
        join_message += f"👤 Игрок: {escape(username)}\n"
        join_message += f"🎮 Игра: {escape(clan.game)}\n"

        if user_profile:
            games = {game.name: game.rank for game in user_profile.games}
            rank = games.get(clan.game, None)
            game = clan.game
            if rank:
                if game in ("Raven 2", "Lineage 2M"):
                    rank = await get_raven2_rank_template(game, rank)
                elif game == "Warcraft":
                    rank = await get_warcraft_rank_template(rank)

            if game in ("Raven 2", "Lineage 2M"):
                join_message += rank
            else:
                join_message += f"📊 Ранг: {rank or 'Не указан'}\n"
            join_message += f"🎯 Цель: {', '.join(user_profile.goals) if user_profile.goals else 'Не указаны'}\n"

        if user_profile.telegram_tag:
            join_message += f"📞 Телеграм: @{escape(user_profile.telegram_tag)}"

        if msg_before_join:
            join_message += (
                f"\n\n✍ Сообщение для лидера клана:\n{escape(msg_before_join)}"
            )

        try:
            leader = await platform_repository.get_profile(clan.platform, clan.user_id)
            if not leader:
                raise RuntimeError("Анкета лидера недоступна")
            contact = await platform_repository.create_contact_request(
                sender_profile_id=user_profile.id,
                target_profile_id=leader.id,
                kind="clan_application",
                game=clan.game,
                message=msg_before_join,
            )
            join_message += (
                f"\n\nПринять: {accept_instruction(leader, contact.id)}"
                f"\nОтветить: {reply_instruction(leader, contact.id)}"
            )
            result = await deliver_text(leader, join_message)
            if not result.delivered:
                await platform_repository.mark_contact_failed(contact.id)
                raise RuntimeError(result.reason or "delivery failed")
            await bot.send_message(
                chat_id=user_id,
                text=TEXT_SENT_MESSAGE,
                reply_markup=await get_back_kb(search_type="clans"),
            )

        except Exception as e:
            await bot.send_message(
                chat_id=user_id,
                text=TEXT_TRIED_TO_SEND_MESSAGE,
                reply_markup=await get_back_kb(search_type="clans"),
            )
            print(e)
    except Exception as e:
        print(e)

    await state.set_state(None)


# async def join_clan(callback: CallbackQuery, state: FSMContext):
#     # await callback.answer()
#     # await callback.message.delete()

#     data = await state.get_data()

#     try:
#         clan_id = int(callback.data.split("_")[-1])
#     except:
#         clan_id = data["clan_id"]

#     data = await state.get_data()
#     clans = data.get("clans", [])

#     clan = next((c for c in clans if c.id == clan_id), None)
#     if not clan:
#         await callback.answer("Клан не найден")
#         return

#     await state.update_data(game=clan.game)

#     user_profile = await repository.get_profile(callback.from_user.id)
#     username = user_profile.nickname if user_profile else callback.from_user.full_name

#     join_message = f"🏰 Заявка на вступление в клан {escape(clan.name)}\n\n"
#     join_message += f"👤 Игрок: {escape(username)}\n"
#     join_message += f"🎮 Игра: {escape(clan.game)}\n"

#     if user_profile:
#         games = {game.name: game.rank for game in await repository.get_games_by_user_id(callback.from_user.id)}
#         rank = games.get(clan.game, None)
#         game = clan.game
#         if rank:
#             if game in ("Raven 2", "Lineage 2M"):
#                 rank = await get_raven2_rank_template(game, rank)
#             elif game == "Warcraft":
#                 rank = await get_warcraft_rank_template(rank)

#         if game in ("Raven 2", "Lineage 2M"):
#             join_message += rank
#         else:
#             join_message += f"📊 Ранг: {rank or 'Не указан'}\n"
#         join_message += f"🎯 Цель: {', '.join(user_profile.goals) if user_profile.goals else 'Не указаны'}\n"

#     if callback.from_user.username:
#         join_message += f"📞 Телеграм: @{escape(callback.from_user.username)}"

#     join_message += "\n\nЧтобы принять пользователя, не стесняйся, напиши ему в личные сообщения"
#     try:
#         keyboard = await get_invite_profile_kb(user_id=user_profile.user_id) if user_profile else None
#         await callback.bot.send_message(
#             chat_id=clan.user_id,
#             text=join_message,
#             reply_markup=keyboard
#         )
#         await callback.message.answer(TEXT_SENT_MESSAGE, reply_markup=await get_back_kb(search_type="clans"))

#         new_xp = user_profile.experience + 30
#         if user_profile.experience // 100 < new_xp // 100:
#             await level_up(callback.bot, user_id=user_profile.user_id, new_level=new_xp // 100 + 1)
#         await repository.add_experience(user_id=user_profile.user_id, experience=30)

#     except Exception as e:
#         await callback.message.answer(TEXT_TRIED_TO_SEND_MESSAGE, reply_markup=await get_back_kb(search_type="clans"))
#         print(e)


@router.callback_query(F.data.startswith("back_to_clans"))
async def back_to_clans(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()

    data = await state.get_data()
    game = data.get("game")

    if game:
        clans = await clan_repository.get_clans_by_game(
            game=game, user_id=callback.from_user.id
        )

        if clans:
            await state.update_data(clans=clans, current_page=0)
            keyboard = await get_clans_kb(clans, page=0)
            await callback.message.edit_text(
                text=TEXT_CLANS_FOUND, reply_markup=keyboard
            )
    await callback.answer()


@router.callback_query(F.data == "close_clans_list")
async def close_clans_list(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "back_to_profiles")
async def get_back_to_profiles(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()

    data = await state.get_data()
    game = data.get("game")
    search_type = data.get("search_type", "profiles")

    if game:
        if search_type == "profiles":
            profiles = await repository.get_profiles_by_game(
                game=game, user_id=callback.from_user.id
            )
            if profiles:
                await state.update_data(profiles=profiles, current_page=0)
                keyboard = await get_profiles_kb(profiles, game=game, page=0)
                await callback.message.answer(
                    text=TEXT_PROFILES_FOUND, reply_markup=keyboard
                )
        elif search_type == "clans":
            clans = await clan_repository.get_clans_by_game(
                game=game, user_id=callback.from_user.id
            )
            if clans:
                await state.update_data(clans=clans, current_page=0)
                keyboard = await get_clans_kb(clans, page=0)
                await callback.message.answer(
                    text=TEXT_CLANS_FOUND, reply_markup=keyboard
                )
    else:
        await callback.message.answer(
            "Я потеряд игру для поиска. Попробуй начать поиск заново."
        )


@router.callback_query(F.data == "close_profiles_list")
async def close_profiles_list(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()

    await callback.message.delete()
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "current_page")
async def handle_current_page(callback: CallbackQuery):
    # await callback.message.delete()

    await callback.answer()


@router.callback_query(F.data == "filter_search")
async def filter_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer(
        TEXT_GAMES, reply_markup=await get_games_filter_search_kb()
    )
    await state.set_state(SearchForm.game)


@router.callback_query(F.data.startswith("filter_game_"))
async def filter_game(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()

    game = callback.data.split("_")[-1]
    await state.update_data(game=game)

    if game == "AION 2":
        await callback.message.answer(
            "Введите сервер AION 2 или напишите «Пропустить»:"
        )
        await state.set_state(SearchForm.aion_server)
    elif game in GAMES_RANKS:
        await callback.message.answer(
            f"Выберите ранг в {game}", reply_markup=await get_ranks_kb(game, True)
        )
        await state.set_state(SearchForm.rank)
    elif game == "Marvel Rivals":
        await callback.message.answer(
            text="Укажите свой ранг Marvel Rivals из списка ниже:",
            reply_markup=await get_marvel_ranks(with_back=True),
        )
        await state.set_state(SearchForm.rank)
    elif game == "Standoff 2":
        await callback.message.answer(
            text="Укажите свой ранг Standoff 2 из списка ниже:",
            reply_markup=await get_standoff_ranks(with_back=True),
        )
        await state.set_state(SearchForm.rank)
    elif game == "Warcraft":
        await callback.message.answer(
            "Выберите режим:", reply_markup=await get_warcraft_modes_kb(True)
        )
        await state.set_state(SearchForm.warcraft_mode)
    elif game in ("Raid Shadow Legends", "WoR"):
        if game == "Raid Shadow Legends":
            await callback.message.answer(
                text=TEXT_RSL, reply_markup=ReplyKeyboardRemove()
            )
        else:
            await callback.message.answer(
                text=TEXT_NUM_RANK, reply_markup=ReplyKeyboardRemove()
            )
        await state.set_state(SearchForm.num_rank)
    elif game in ("Raven 2", "Lineage 2M"):
        if game == "Raven 2":
            from utils.raven import CLUSTER_TEXT

            await callback.message.answer(
                text=CLUSTER_TEXT,
                reply_markup=await get_raven_clusters_kb(with_back=True, skip=True),
            )
            await state.set_state(SearchForm.raven_cluster)
        else:
            from utils.lineage import SERVER_TEXT

            await state.update_data(lineage_skip_option=True)
            await callback.message.answer(
                text=SERVER_TEXT,
                reply_markup=await get_lineage_servers_pt_1(with_back=True, skip=True),
            )
            await state.set_state(SearchForm.lineage_server)


@router.message(SearchForm.aion_server)
async def search_aion_server(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введите сервер или напишите «Пропустить»:")
        return
    server = (
        None if message.text.strip().lower() == "пропустить" else message.text.strip()
    )
    await state.update_data(server=server)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Любая", callback_data="search_aion_faction_skip"
                )
            ],
            *[
                [
                    InlineKeyboardButton(
                        text=value, callback_data=f"search_aion_faction_{value}"
                    )
                ]
                for value in AION_2_FACTIONS
            ],
        ]
    )
    await message.answer("Выберите фракцию AION 2:", reply_markup=markup)
    await state.set_state(SearchForm.aion_faction)


@router.callback_query(
    SearchForm.aion_faction, F.data.startswith("search_aion_faction_")
)
async def search_aion_faction(callback: CallbackQuery, state: FSMContext):
    value = callback.data.removeprefix("search_aion_faction_")
    await state.update_data(faction=None if value == "skip" else value)
    await callback.message.edit_text(
        f"Фракция: {'Любая' if value == 'skip' else value}", reply_markup=None
    )
    await callback.message.answer("Введите ранг/уровень или напишите «Пропустить»:")
    await state.set_state(SearchForm.aion_rank)
    await callback.answer()


@router.message(SearchForm.aion_rank)
async def search_aion_rank(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введите ранг или напишите «Пропустить»:")
        return
    rank = (
        None if message.text.strip().lower() == "пропустить" else message.text.strip()
    )
    await state.update_data(rank=rank)
    await message.answer("Выберите цель:", reply_markup=await get_goals_kb(True))
    await state.set_state(SearchForm.goal)


@router.message(SearchForm.num_rank)
async def save_num_rank(message: Message, state: FSMContext):
    if message.text:
        try:
            float(message.text)
        except Exception as e:
            print(e)
            await message.answer("Напиши число.")
            return

        await state.update_data(game_rank=message.text)
        await message.answer("Выберите цель:", reply_markup=await get_goals_kb(True))
        await state.set_state(SearchForm.goal)
    else:
        await message.answer("Напиши число.")


@router.callback_query(SearchForm.rank)
async def save_rank(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data["game"]

    text = callback.data.split("_")[-1]
    await callback.message.delete()

    if text:
        if text == "back":
            await callback.message.answer(
                "Выберите игру:", reply_markup=await get_games_filter_search_kb()
            )
            await state.set_state(SearchForm.game)
            return

        elif text == "skip":
            await state.update_data(rank=None)

        elif game == "Marvel Rivals":
            await state.update_data(rank=text)

        elif game == "Standoff 2":
            await state.update_data(rank=text)

        elif text in GAMES_RANKS[game]:
            await state.update_data(rank=text)

        await callback.message.answer(
            "Выберите цель:", reply_markup=await get_goals_kb(True)
        )
        await state.set_state(SearchForm.goal)


@router.callback_query(SearchForm.warcraft_mode)
async def save_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = callback.data.split("_")[-1]
    await callback.message.delete()

    if text:
        if text in WARCRAFT_MODES:
            await state.update_data(mode=text)
            is_pve = text == "PvE"
            await callback.message.answer(
                "Выберите рейтинг:",
                reply_markup=await get_warcraft_ranks_kb(is_pve=is_pve),
            )
            await state.set_state(SearchForm.warcraft_rank)
        elif text == "skip":
            await state.update_data(rank=None)
            await callback.message.answer(
                "Выберите цель:", reply_markup=await get_goals_kb(True)
            )
            await state.set_state(SearchForm.goal)
        elif text == "back":
            await callback.message.answer(
                "Выберите режим:", reply_markup=await get_warcraft_modes_kb(True)
            )
            await state.set_state(SearchForm.warcraft_mode)
        else:
            await callback.message.answer("Выберите ответ из списка!")
    else:
        await callback.message.answer("Ответьте текстом!")


@router.callback_query(SearchForm.warcraft_rank)
async def save_warcraft_rank(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    if callback.data == "back_from_warcraft_ranks":
        await callback.message.answer(
            text=TEXT_WARCRAFT_MODE, reply_markup=await get_warcraft_modes_kb(True)
        )
        await state.set_state(SearchForm.warcraft_mode)
        return
    elif callback.data.startswith("ranks_page_"):
        await handle_ranks_pagination(callback, state)
        return

    parts = callback.data.split("/")
    if len(parts) >= 3 and parts[0] == "add_warcraft_rank":
        try:
            rank_index = int(parts[1])
            is_pve_str = parts[2]
            is_pve = is_pve_str.lower() == "true"
            # Get the actual rank based on the stored state or recreate the list
            ranks = WARCRAFT_PvE if is_pve else WARCRAFT
            if 0 <= rank_index < len(ranks):
                rank = ranks[rank_index]
                await callback.message.delete()
            else:
                await callback.message.answer(
                    "Произошла какая-то ошибка... Попытайтесь позже"
                )
                return
        except (ValueError, IndexError) as e:
            await callback.message.answer(
                "Произошла какая-то ошибка... Попытайтесь позже"
            )
            print(e)
            return
    else:
        await callback.message.answer("Произошла какая-то ошибка... Попытайтесь позже")
        return

    data = await state.get_data()

    await state.update_data(rank=data["mode"] + "/" + rank + ";")

    await callback.message.answer(
        "Выберите цель:", reply_markup=await get_goals_kb(True)
    )
    await state.set_state(SearchForm.goal)


@router.callback_query(SearchForm.goal)
async def save_goal(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data["game"]

    await callback.answer()
    await callback.message.delete()
    text = callback.data.split("_")[-1]

    if text:
        if text == "back":  # Добавить игры!!!
            if game == "Marvel Rivals":
                await callback.message.answer(
                    text="Укажите свой ранг Marvel Rivals из списка ниже:",
                    reply_markup=await get_marvel_ranks(with_back=True),
                )
                await state.set_state(SearchForm.rank)
            elif game == "AION 2":
                await callback.message.answer(
                    "Введите сервер AION 2 или напишите «Пропустить»:"
                )
                await state.set_state(SearchForm.aion_server)
            elif game == "Warcraft":
                await callback.message.answer(
                    "Выберите режим:", reply_markup=await get_warcraft_modes_kb(True)
                )
                await state.set_state(SearchForm.warcraft_mode)
            elif game in ("Raid Shadow Legends", "WoR"):
                if game == "Raid Shadow Legends":
                    await callback.message.answer(
                        text=TEXT_RSL, reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    await callback.message.answer(
                        text=TEXT_NUM_RANK, reply_markup=ReplyKeyboardRemove()
                    )
                await state.set_state(SearchForm.num_rank)
            elif game in ("Raven 2", "Lineage 2M"):
                if game == "Raven 2":
                    from utils.raven import CLUSTER_TEXT

                    await callback.message.answer(
                        text=CLUSTER_TEXT,
                        reply_markup=await get_raven_clusters_kb(
                            with_back=True, skip=True
                        ),
                    )
                    await state.set_state(SearchForm.raven_cluster)
                else:
                    from utils.lineage import SERVER_TEXT

                    await state.update_data(lineage_skip_option=True)
                    await callback.message.answer(
                        text=SERVER_TEXT,
                        reply_markup=await get_lineage_servers_pt_1(
                            with_back=True, skip=True
                        ),
                    )
                    await state.set_state(SearchForm.lineage_server)
            else:
                await callback.message.answer(
                    f"Выберите ранг в {game}",
                    reply_markup=await get_ranks_kb(game, True),
                )
                await state.set_state(SearchForm.rank)
            return

        elif text == "skip":
            await state.update_data(goal=None)

        elif text in GOALS_LIST:
            await state.update_data(goal=text)

    await state.update_data(user_id=callback.from_user.id)

    await get_profiles_by_filter(callback.message, state)


@router.callback_query(F.data == "profile_by_filters")
async def get_profiles_by_filter_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()
    await get_profiles_by_filter(callback.message, state)


async def get_profiles_by_filter(message: Message, state: FSMContext):
    data = await state.get_data()
    game = data["game"]
    rank = data.get("rank", None)
    goal = data.get("goal", None)
    server = data.get("server")
    faction = data.get("faction")
    user_id = data["user_id"]
    if game not in ("Raven 2", "Lineage 2M"):
        profiles = await repository.get_profiles_by_filters(
            user_id=user_id,
            game=game,
            rank=rank,
            goal=goal,
            server=server,
            faction=faction,
        )
    else:
        print(rank)
        profiles = await repository.get_raven_profiles(
            user_id=user_id, rank=rank, goal=goal, game=game
        )

    if profiles:
        await state.update_data(
            profiles=profiles, current_page=0, game=game, search_type="profiles"
        )

        keyboard = await get_profiles_kb(profiles, game=game, page=0, need_filter=True)
        await message.answer(text=TEXT_PROFILES_FOUND, reply_markup=keyboard)
    else:
        await message.answer(
            text=TEXT_NO_PROFILES.format(game=game),
            reply_markup=await get_back_to_games_kb("profiles"),
        )
        await state.clear()


@router.callback_query(F.data == "emoji_means")
async def emoji_means(callback: CallbackQuery):
    await callback.answer()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удалить", callback_data="delete_emoji")]
        ]
    )

    await callback.message.answer(TEXT_EMOJI, reply_markup=kb)


@router.callback_query(F.data == "delete_emoji")
async def delete_emoji(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
