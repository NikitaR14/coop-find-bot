from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from states.create_profile import *
from keyboards.profile_kb import *
from utils.constants import *
from repositories.profile_repository import profile_repository as repository
from handlers.menu import cmd_menu
from .edit_profile import start_edit_profile_message
from utils.creation_process import restrict_access, CMDS
from typing import Union
from statistic import Statistic
import asyncio
from html import escape


router = Router()


### ТЕКСТЫ
TEXT_NICK = "Укажи игровой ник, под которым тебя будут видеть другие игроки."
TEXT_AGE = "Укажи свой возраст (по желанию)."
TEXT_TAG = "Укажи свой тег в Telegram (по желанию)."
TEXT_GENDER = "Выбери свой пол."
TEXT_GAME = "Выбери игры, в которую ищешь тиммейтов:"
TEXT_RANK = "Укажи свой ранг/уровень в {game}:"
TEXT_ABOUT = "Расскажи немного о себе. Например, опиши свои интересы, опыт игры, укажи UID (по желанию):"
TEXT_GOAL = "Укажи свою цель поиска: (например: для общения, для буст рейтинга и т.д.)"
TEXT_PHOTO = "Отправь фото профиля."
TEXT_SUCCESS = (
    "Отлично! Твоя анкета успешно создана и теперь доступна другим игрокам. 👾"
)
TEXT_ALLOW_INVITATIONS = "Разрешить присылать приглашения в игру от других пользователей? При отклонении ты сможешь отправлять сообщения самостоятельно. "
TEXT_SKIP = (
    '\n\n<i>Если не хочешь заполнять эту информацию, напиши в чат "Пропустить"</i>'
)
TEXT_ANSWER_TYPE_ERROR = "Ответь текстом."
TEXT_WRONG_ANSWER = "Выберите ответ из предложенного списка!"
TEXT_PHOTO_ERROR = 'Пришлите фотографию профиля или выберите доступный вариант ответа ("Фото с профиля" или "Пропустить")'
TEXT_PHOTO_COUNT_ERROR = "Пришлите 1 фотографию"
TEXT_REPEAT_PROFILE = "Заполни заново свою анкету"
TEXT_ACCEPTED = "\n\nПодтвеждено ✅"
TEXT_REJECTED = "\n\nОтклонено ❌"
TEXT_ALREADY_HAVE_PROFILE = "У тебя уже есть анкета.\nТы можешь ее удалить или изменить"
IS_PROFILE_OK = "Все верно?"
TEXT_ADD_GAME = "Добавить еще игру?"
CALLBACK_BACK = "back"
TEXT_BACK = "Назад"
TEXT_WARCRAFT_MODE = "Выбери режим из списка, в котором хочешь указать рейтинг:"
TEXT_NUM_RANK = "Введи силу аккаунта числом:"
TEXT_GALLERY = "Отправь скриншоты игрового профиля, до 10 шт. (по желанию)"
TEXT_TIME = "Выбери, пожалуйста, удобное время для игры по МСК:"
TEXT_RSL = """
Введи силу аккаунта в миллионах 🌟
Если сила меньше 1 млн — впиши дробное значение.

Пример: 500 000 тыс = 0,5 млн
"""

# В хендлерах замените вызовы клавиатур на:


@router.callback_query(F.data == "create_profile")
async def start_profile_with_message(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.update_data(
        user_id=callback.from_user.id, chat_id=callback.message.chat.id
    )
    await callback.answer()

    await start_profile(bot=callback.bot, state=state)


async def start_profile(bot: Bot, state: FSMContext):
    data = await state.get_data()
    user_id = data["user_id"]
    chat_id = data["chat_id"]

    if not await repository.get_profile(user_id=user_id):
        await bot.send_message(
            chat_id=chat_id, text=TEXT_NICK, reply_markup=await get_back_kb()
        )
        await state.update_data(
            games={},
            game=None,
            game_rank="",
            goals=[],
            process="creating_profile",
            time=[],
        )
        await state.set_state(ProfileForm.nickname)
    else:
        await bot.send_message(chat_id=chat_id, text=TEXT_ALREADY_HAVE_PROFILE)


@router.message(ProfileForm.nickname)
async def save_nickname(message: Message, state: FSMContext):
    if message.text in CMDS:
        await restrict_access(message, TEXT_NICK, get_back_kb)
        return

    if message.text == TEXT_BACK:
        await message.answer(
            "Создание анкеты отменено.", reply_markup=await get_back_to_menu()
        )
        await state.clear()
        return

    if message.text:
        await state.update_data(nickname=message.text)
        await message.answer(text=TEXT_AGE, reply_markup=await get_back_kb(skip=True))
        await state.set_state(ProfileForm.age)
    else:
        await message.answer(
            text="Напиши свой ник текстом (до 32 символов)",
            reply_markup=await get_back_kb(),
        )
        await state.set_state(ProfileForm.nickname)


@router.message(ProfileForm.age)
async def save_age(message: Message, state: FSMContext):
    if message.text in CMDS:
        await restrict_access(message, TEXT_AGE, get_back_kb, skip=True)
        return
    if message.text == TEXT_BACK:
        await message.answer(text=TEXT_NICK, reply_markup=await get_back_kb())
        await state.set_state(ProfileForm.nickname)
        return
    if message.text == "Пропустить":
        age = None
    else:
        try:
            age = int(message.text)
        except (TypeError, ValueError):
            await message.answer("Возраст должен быть числом или нажми «Пропустить».")
            return
        if age < 13 or age > 120:
            await message.answer("Укажи возраст от 13 до 120 лет.")
            return
    await state.update_data(age=age)
    await message.answer(text=TEXT_TAG, reply_markup=await get_tag_kb())
    await state.set_state(ProfileForm.telegram_tag)


@router.message(ProfileForm.telegram_tag)
async def save_telegram_tag(message: Message, state: FSMContext):
    if message.text in CMDS:
        await restrict_access(message, TEXT_TAG, get_tag_kb)
        return

    if message.text == TEXT_BACK:
        await message.answer(text=TEXT_AGE, reply_markup=await get_back_kb(skip=True))
        await state.set_state(ProfileForm.age)
        return

    if message.text:
        if message.text == "Пропустить":
            await state.update_data(telegram_tag=None)
        elif message.text == "Отправить данные":
            await state.update_data(telegram_tag=message.from_user.username)
        else:
            await state.update_data(telegram_tag=message.text)

        await message.answer(
            text=TEXT_GENDER, reply_markup=await get_gender_keyboard(with_back=True)
        )
        await state.set_state(ProfileForm.gender)
    else:
        await message.answer(
            text=TEXT_ANSWER_TYPE_ERROR, reply_markup=await get_tag_kb()
        )
        await state.set_state(ProfileForm.telegram_tag)


@router.message(ProfileForm.gender)
@router.callback_query(ProfileForm.gender)
async def save_gender(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(
                event, TEXT_GENDER, get_gender_keyboard, with_back=True
            )
            return
    else:
        callback = event

    await callback.answer()
    text = callback.data.split("_")[-1]

    if text == CALLBACK_BACK:
        await callback.message.answer(text=TEXT_TAG, reply_markup=await get_tag_kb())
        await state.set_state(ProfileForm.telegram_tag)
        return

    if text:
        if text == "skip":
            await state.update_data(gender=None)
        else:
            if text in GENDER_LIST:
                await state.update_data(gender=text)
            else:
                await callback.message.answer(
                    text=TEXT_WRONG_ANSWER, reply_markup=await get_gender_keyboard()
                )
                await state.set_state(ProfileForm.gender)
                return

        await callback.message.edit_text(
            text=TEXT_GENDER + f"\nВыбрано: {text if text != 'skip' else 'Пропустить'}",
            reply_markup=None,
        )

        await callback.message.answer(
            text=TEXT_GAME, reply_markup=await get_game_kb(with_back=True)
        )
        await state.set_state(ProfileForm.game)
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR, reply_markup=await get_gender_keyboard()
        )
        await state.set_state(ProfileForm.gender)


@router.message(ProfileForm.game)
@router.callback_query(ProfileForm.game)
async def save_game(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(event, TEXT_GAME, get_game_kb, with_back=True)
            return
    else:
        callback = event

    if callback.data == "back_from_games":
        await callback.message.answer(
            text=TEXT_GENDER, reply_markup=await get_gender_keyboard()
        )
        await state.set_state(ProfileForm.gender)
        await callback.answer()
        return

    game = callback.data.split("_")[-1]

    data = await state.get_data()
    games = data["games"]

    await callback.answer()

    if game:
        if game in GAME_LIST:
            if game not in games:
                await state.update_data(game=game)
            else:
                await callback.message.answer(text="Ты уже выбрал эту игру!")
                await callback.message.answer(
                    text=TEXT_ADD_GAME,
                    reply_markup=await get_confirmation_kb(with_back=True),
                )
                await state.set_state(ProfileForm.add_new_game)
                return
        else:
            await callback.message.answer(
                text=TEXT_WRONG_ANSWER, reply_markup=await get_game_kb(with_back=True)
            )
            await state.set_state(ProfileForm.game)
            return

        if game == "AION 2":
            await callback.message.answer(
                "Введите название сервера AION 2:", reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(ProfileForm.aion_server)
        elif game in GAMES_RANKS:
            await callback.message.answer(
                text=TEXT_RANK.format(game=game),
                reply_markup=await get_ranks_kb(game, with_back=True),
            )
            await state.set_state(ProfileForm.rank)
        elif game == "Marvel Rivals":
            await callback.message.answer(
                text="Укажите свой ранг Marvel Rivals из списка ниже:",
                reply_markup=await get_marvel_ranks(with_back=True),
            )
            await state.set_state(ProfileForm.rank)
        elif game == "Standoff 2":
            await callback.message.answer(
                text="Выберите ранг Standoff 2 из списка ниже:",
                reply_markup=await get_standoff_ranks(with_back=True),
            )
            await state.set_state(ProfileForm.rank)
        elif game == "Warcraft":
            await callback.message.answer(
                text=TEXT_WARCRAFT_MODE, reply_markup=await get_warcraft_modes_kb(True)
            )
            await state.set_state(ProfileForm.add_warcraft_mode)
        elif game == "Raid Shadow Legends":
            await callback.message.answer(
                text=TEXT_RSL, reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(ProfileForm.num_rank)
        elif game == "WoR":
            await callback.message.answer(
                text=TEXT_NUM_RANK, reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(ProfileForm.num_rank)
        elif game == "Raven 2":
            from utils.raven import CLUSTER_TEXT

            await callback.message.answer(
                text=CLUSTER_TEXT,
                reply_markup=await get_raven_clusters_kb(with_back=True),
            )
            await state.set_state(ProfileForm.raven_cluster)
        elif game == "Lineage 2M":
            from utils.lineage import SERVER_TEXT

            await callback.message.answer(
                text=SERVER_TEXT,
                reply_markup=await get_lineage_servers_pt_1(with_back=True),
            )
            await state.set_state(ProfileForm.lineage_server)

        await callback.message.edit_text(
            text=f"Выбрана игра: {game}", reply_markup=None
        )
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR, reply_markup=await get_game_kb(with_back=True)
        )
        await state.set_state(ProfileForm.game)


@router.message(ProfileForm.aion_server)
async def save_aion_player_server(message: Message, state: FSMContext):
    if not message.text or message.text in CMDS:
        await message.answer("Введите название сервера AION 2:")
        return
    await state.update_data(game_server=message.text.strip())
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=value, callback_data=f"aion_player_faction_{value}"
                )
            ]
            for value in AION_2_FACTIONS
        ]
    )
    await message.answer("Выберите фракцию AION 2:", reply_markup=markup)
    await state.set_state(ProfileForm.aion_faction)


@router.callback_query(
    ProfileForm.aion_faction, F.data.startswith("aion_player_faction_")
)
async def save_aion_player_faction(callback: CallbackQuery, state: FSMContext):
    faction = callback.data.removeprefix("aion_player_faction_")
    if faction not in AION_2_FACTIONS:
        await callback.answer(TEXT_WRONG_ANSWER, show_alert=True)
        return
    await state.update_data(game_faction=faction)
    await callback.message.edit_text(f"Фракция: {faction}", reply_markup=None)
    await callback.message.answer(
        "Введите ранг/уровень AION 2 или напишите «Пропустить»:"
    )
    await state.set_state(ProfileForm.aion_rank)
    await callback.answer()


@router.message(ProfileForm.aion_rank)
async def save_aion_player_rank(message: Message, state: FSMContext):
    if not message.text or message.text in CMDS:
        await message.answer("Введите ранг или напишите «Пропустить»:")
        return
    rank = "" if message.text.strip().lower() == "пропустить" else message.text.strip()
    await state.update_data(game_rank=rank)
    await message.answer(
        text=TEXT_GALLERY, reply_markup=await get_skip_keyboard(with_back=True)
    )
    await state.set_state(ProfileForm.gallery)


@router.message(ProfileForm.num_rank)
async def save_num_rank(message: Message, state: FSMContext):
    data = await state.get_data()
    game = data["game"]
    if message.text in CMDS:
        if game == "Raid Shadow Legends":
            await restrict_access(message, TEXT_RSL, ReplyKeyboardRemove)
        else:
            await restrict_access(message, TEXT_NUM_RANK, ReplyKeyboardRemove)
        return

    if message.text:
        try:
            float(message.text)
        except Exception as e:
            print(e)
            await message.answer("Напиши число.")
            return

        await state.update_data(game_rank=message.text)
        await message.answer(
            text=TEXT_GALLERY, reply_markup=await get_skip_keyboard(with_back=True)
        )
        await state.set_state(ProfileForm.gallery)
    else:
        await message.answer("Напиши число.")


@router.message(ProfileForm.add_warcraft_mode)
@router.callback_query(ProfileForm.add_warcraft_mode)
async def save_mode(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(
                event, TEXT_WARCRAFT_MODE, get_warcraft_modes_kb, True
            )
            return
    else:
        callback = event

    await callback.answer()
    text = callback.data.split("_")[-1]
    if text == CALLBACK_BACK:
        await callback.message.answer(
            text=TEXT_GAME, reply_markup=await get_game_kb(with_back=True)
        )
        await state.set_state(ProfileForm.game)
        return

    if text:
        if text in WARCRAFT_MODES + ["skip"]:
            data = await state.get_data()
            rank = data["game_rank"]

            if text not in rank:
                if text == "skip":
                    if rank:
                        rank += ""
                    else:
                        rank = ""

                    await state.update_data(game_rank=rank)

                    await callback.message.answer(
                        text=TEXT_GALLERY,
                        reply_markup=await get_skip_keyboard(with_back=True),
                    )
                    await state.set_state(ProfileForm.gallery)

                else:
                    mode = text
                    await state.update_data(mode=mode)
                    is_pve = mode == "PvE"
                    await state.update_data(is_pve=is_pve)  # Костыль

                    await callback.message.answer(
                        text="Выбери рейтинг из списка:",
                        reply_markup=await get_warcraft_ranks_kb(is_pve=is_pve),
                    )
                    await state.set_state(ProfileForm.add_warcraft_rank)

                await callback.message.edit_text(
                    f"Выбран режим: {text if text != 'skip' else 'Пропустить'}",
                    reply_markup=None,
                )
            else:
                await callback.message.answer(
                    "Вы уже выбрали этот режим. Выберите другой."
                )

        else:
            await callback.message.answer("Выберите режим из предложенного списка.")
    else:
        await callback.message.answer(text=TEXT_ANSWER_TYPE_ERROR)


@router.message(ProfileForm.add_warcraft_rank)
@router.callback_query(ProfileForm.add_warcraft_rank)
async def save_warcraft_rank(event: Union[CallbackQuery, Message], state: FSMContext):
    data = await state.get_data()
    is_pve = data.get("is_pve", False)
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(
                event, "Выбери рейтинг из списка:", get_warcraft_ranks_kb, is_pve=is_pve
            )
            return
    else:
        callback = event

    await callback.answer()

    if callback.data == "back_from_warcraft_ranks":
        await callback.message.answer(
            text=TEXT_WARCRAFT_MODE, reply_markup=await get_warcraft_modes_kb(True)
        )
        await state.set_state(ProfileForm.add_warcraft_mode)
        return
    elif callback.data.startswith("ranks_page_"):
        await handle_ranks_pagination(callback, state)
        return

    # Parse the callback data to get index and is_pve flag
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
                await callback.message.edit_text(
                    f"Выбран рейтинг: {rank}", reply_markup=None
                )
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
    games = data["games"]
    game = data["game"]
    game_rank = data["game_rank"]
    mode = data["mode"]

    new_rank = game_rank + f"{mode}/{rank};"

    await state.update_data(games=games, game=game, mode=None, game_rank=new_rank)

    await callback.message.edit_text(f"Выбран ранг: {rank}", reply_markup=None)

    await callback.message.answer(
        "Выбери режим из списка, в котором хочешь указать рейтинг:",
        reply_markup=await get_warcraft_modes_kb(True),
    )
    await state.set_state(ProfileForm.add_warcraft_mode)


async def handle_ranks_pagination(callback: CallbackQuery, state: FSMContext):
    # await callback.message.delete()

    page = int(callback.data.split("_")[-1])
    mode = callback.data.split("_")[-2]
    data = await state.get_data()

    await state.update_data(current_page=page)
    keyboard = (
        await get_warcraft_ranks_kb(is_pve=True, page=page)
        if mode == "pve"
        else await get_warcraft_ranks_kb(is_pve=False, page=page)
    )
    await callback.message.edit_reply_markup(reply_markup=keyboard)

    await callback.answer()


@router.message(ProfileForm.rank)
@router.callback_query(ProfileForm.rank)
async def save_rank(event: Union[CallbackQuery, Message], state: FSMContext):
    data = await state.get_data()
    game = data["game"]

    if isinstance(event, Message):
        if event.text in CMDS:
            if game == "Marvel Rivals":
                await restrict_access(
                    event,
                    "Укажите свой ранг Marvel Rivals из списка ниже:",
                    get_marvel_ranks,
                    with_back=True,
                )
            elif game == "Standoff 2":
                await restrict_access(
                    event,
                    "Выберите ранг Standoff 2 из списка ниже:",
                    get_standoff_ranks,
                    with_back=True,
                )
            else:
                await restrict_access(
                    event,
                    TEXT_RANK.format(game=game),
                    get_ranks_kb,
                    game,
                    with_back=True,
                )
            return
    else:
        callback = event

    await callback.answer()
    text = callback.data.split("_")[-1]

    if text:
        if text == CALLBACK_BACK:
            await callback.message.answer(
                text=TEXT_GAME, reply_markup=await get_game_kb(with_back=True)
            )
            await state.set_state(ProfileForm.game)
            return

        elif text == "skip":
            await state.update_data(game_rank="")

        elif game == "Marvel Rivals":
            await state.update_data(game_rank=text)
        elif game == "Standoff 2":
            await state.update_data(game_rank=text)
        elif text in GAMES_RANKS[game]:
            await state.update_data(game_rank=text)

        else:
            await callback.message.answer("Выбрано некорректное значение!")
            # await callback.message.answer(text=TEXT_RANK.format(game=game), reply_markup=await get_ranks_kb(game, with_back=True))
            return

        await callback.message.edit_text(
            f"Выбран ранг: {text if text != 'skip' else 'Пропустить'}",
            reply_markup=None,
        )
        await callback.message.answer(
            text=TEXT_GALLERY, reply_markup=await get_skip_keyboard(with_back=True)
        )
        await state.set_state(ProfileForm.gallery)
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR,
            reply_markup=await get_skip_keyboard(with_back=True),
        )
        await state.set_state(ProfileForm.rank)


@router.message(ProfileForm.gallery)
async def save_gallery(
    message: Message, state: FSMContext, album: list[Message] = None
):
    if message.text in CMDS:
        await restrict_access(message, TEXT_GALLERY, get_skip_keyboard, with_back=True)
        return

    data = await state.get_data()
    games = data["games"]
    game = data["game"]
    rank = data["game_rank"]

    if message.photo:
        if album:
            if len(album) <= 10:
                games[game] = {
                    "rank": rank,
                    "gallery": [photo.photo[-1].file_id for photo in album],
                    "server": data.get("game_server") if game == "AION 2" else None,
                    "faction": data.get("game_faction") if game == "AION 2" else None,
                }

                await state.update_data(games=games, game=game, game_rank=rank)

            else:
                await message.answer("Отправьте до 10 фотографий.")
                return
        else:
            games[game] = {
                "rank": rank,
                "gallery": [message.photo[-1].file_id],
                "server": data.get("game_server") if game == "AION 2" else None,
                "faction": data.get("game_faction") if game == "AION 2" else None,
            }
            await state.update_data(games=games, game=game, game_rank=rank)

        await message.answer(
            "Подгрузил твои фотографии. Не благодари🔥",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            text=TEXT_ADD_GAME, reply_markup=await get_confirmation_kb(with_back=True)
        )
        await state.set_state(ProfileForm.add_new_game)

    elif message.text:
        if message.text == "Пропустить":
            games[game] = {
                "rank": rank,
                "gallery": [],
                "server": data.get("game_server") if game == "AION 2" else None,
                "faction": data.get("game_faction") if game == "AION 2" else None,
            }

            await state.update_data(games=games, game=game, game_rank=rank)
            await message.answer(
                "Подгрузил твои фотографии. Не благодари🔥",
                reply_markup=ReplyKeyboardRemove(),
            )
            await message.answer(
                text=TEXT_ADD_GAME,
                reply_markup=await get_confirmation_kb(with_back=True),
            )
            await state.set_state(ProfileForm.add_new_game)

        elif message.text == "Назад":
            if game in GAMES_RANKS:
                await message.answer(
                    text=TEXT_RANK.format(game=game),
                    reply_markup=await get_ranks_kb(game, with_back=True),
                )
                await state.set_state(ProfileForm.rank)
            elif game == "Marvel Rivals":
                await message.answer(
                    text="Укажите свой ранг Marvel Rivals из списка ниже:",
                    reply_markup=await get_marvel_ranks(with_back=True),
                )
                await state.set_state(ProfileForm.rank)
            elif game == "Standoff 2":
                await message.answer(
                    text="Выберите ранг Standoff 2 из списка ниже:",
                    reply_markup=await get_standoff_ranks(with_back=True),
                )
                await state.set_state(ProfileForm.rank)
            elif game == "Warcraft":
                await message.answer(
                    text=TEXT_WARCRAFT_MODE,
                    reply_markup=await get_warcraft_modes_kb(True),
                )
                await state.set_state(ProfileForm.add_warcraft_mode)
            elif game == ("WoR", "Raid Shadow Legends"):
                if game == "Raid Shadow Legends":
                    await message.answer(
                        text=TEXT_RSL, reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    await message.answer(
                        text=TEXT_NUM_RANK, reply_markup=ReplyKeyboardRemove()
                    )
                await state.set_state(ProfileForm.num_rank)
            elif game in ("Raven 2", "Lineage 2M"):
                await message.answer(
                    text=TRANSFER_TEXT,
                    reply_markup=await get_confirmation_kb(with_back=True, skip=True),
                )
                await state.set_state(ProfileForm.transfer)
        else:
            await message.answer("Пришлите фотографии или выберите ответ с клавиатуры!")


@router.message(ProfileForm.add_new_game)
@router.callback_query(ProfileForm.add_new_game)
async def add_new_game(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(
                event, TEXT_ADD_GAME, get_confirmation_kb, with_back=True
            )
            return
    else:
        callback = event

    await callback.answer()
    await callback.message.delete()
    text = callback.data.split("_")[-1]
    if text == CALLBACK_BACK:
        data = await state.get_data()

        await callback.message.answer(
            text=TEXT_GALLERY, reply_markup=await get_skip_keyboard(with_back=True)
        )
        await state.set_state(ProfileForm.gallery)
        return

    if text:
        if text == "Да":
            await callback.message.answer(
                text=TEXT_GAME, reply_markup=await get_game_kb(with_back=True)
            )
            await state.set_state(ProfileForm.game)
        elif text == "Нет":
            await callback.message.answer(
                text=TEXT_TIME, reply_markup=await get_time_kb(True)
            )
            await state.set_state(ProfileForm.time)
        else:
            await callback.message.answer(
                text=TEXT_WRONG_ANSWER,
                reply_markup=await get_confirmation_kb(with_back=True),
            )
            await state.set_state(ProfileForm.add_new_game)
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR,
            reply_markup=await get_confirmation_kb(with_back=True),
        )
        await state.set_state(ProfileForm.add_new_game)


@router.message(ProfileForm.time)
@router.callback_query(ProfileForm.time)
async def save_time(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(event, TEXT_TIME, get_time_kb, with_back=True)
            return
    else:
        callback = event

    await callback.answer()
    text = callback.data.split("_")[-1]
    data = await state.get_data()
    time = data["time"]

    if text == CALLBACK_BACK:
        await callback.message.answer(
            text=TEXT_ADD_GAME, reply_markup=await get_confirmation_kb(with_back=True)
        )
        await state.set_state(ProfileForm.add_new_game)
        return

    if text:
        if text in CONVENIENT_TIME:
            if text not in time:
                time.append(text)
                await state.update_data(time=time)
                await callback.message.edit_text(
                    f"Выбрано время: {text}", reply_markup=None
                )
                await callback.message.answer(
                    text="Добавить еще промежуток время?",
                    reply_markup=await get_confirmation_kb(with_back=True),
                )
                await state.set_state(ProfileForm.add_new_time)
            else:
                await callback.message.answer(
                    "Вы уже выбрали этот промежуток времени. Теперь выберите другой:",
                    reply_markup=await get_time_kb(with_back=True),
                )
        else:
            await callback.message.answer(text="Выбери промежуток времени из списка.")
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR, reply_markup=await get_time_kb(with_back=True)
        )


@router.message(ProfileForm.add_new_time)
@router.callback_query(ProfileForm.add_new_time)
async def add_new_time(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(
                event,
                "Добавить еще промежуток время?",
                get_confirmation_kb,
                with_back=True,
            )
            return
    else:
        callback = event

    await callback.answer()
    await callback.message.delete()
    text = callback.data.split("_")[-1]

    if text == CALLBACK_BACK:
        data = await state.get_data()
        time = data["time"]

        if time:
            time.pop()
            await state.update_data(time=time)

            if time:  # Если остались игры, возвращаемся к выбору добавления
                await callback.message.answer(
                    text="Добавить еще промежуток времени?",
                    reply_markup=await get_confirmation_kb(with_back=True),
                )
                await state.set_state(ProfileForm.add_new_time)
            else:  # Если игр не осталось, возвращаемся к выбору первой игры
                await callback.message.answer(
                    text=TEXT_TIME, reply_markup=await get_time_kb(with_back=True)
                )
                await state.set_state(ProfileForm.time)
        return

    if text:
        if text == "Да":
            await callback.message.answer(
                text=TEXT_TIME, reply_markup=await get_time_kb(with_back=True)
            )
            await state.set_state(ProfileForm.time)
        elif text == "Нет":
            await callback.message.answer(
                text=TEXT_ABOUT, reply_markup=await get_back_kb()
            )
            await state.set_state(ProfileForm.about)
        else:
            await callback.message.answer(
                text=TEXT_WRONG_ANSWER,
                reply_markup=await get_confirmation_kb(with_back=True),
            )
            await state.set_state(ProfileForm.add_new_time)
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR,
            reply_markup=await get_confirmation_kb(with_back=True),
        )
        await state.set_state(ProfileForm.add_new_time)


@router.message(ProfileForm.about)
async def save_about(message: Message, state: FSMContext):
    if message.text in CMDS:
        await restrict_access(message, TEXT_ABOUT, get_back_kb)
        return

    if message.text == TEXT_BACK:
        await message.answer(
            text="Добавить еще промежуток времени?",
            reply_markup=await get_confirmation_kb(with_back=True),
        )
        await state.set_state(ProfileForm.add_new_time)
        return

    if message.text:
        await state.update_data(about=message.text)
        await message.answer(
            text=TEXT_GOAL, reply_markup=await get_goals_kb(with_back=True)
        )
        await state.set_state(ProfileForm.goal)
    else:
        await message.answer(
            text=TEXT_ANSWER_TYPE_ERROR, reply_markup=await get_back_kb()
        )
        await state.set_state(ProfileForm.about)


@router.message(ProfileForm.goal)
@router.callback_query(ProfileForm.goal)
async def save_goal(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(event, TEXT_GOAL, get_goals_kb, with_back=True)
            return
    else:
        callback = event

    await callback.answer()
    text = callback.data.split("_")[-1]

    data = await state.get_data()
    goals = data["goals"]

    if text == CALLBACK_BACK:
        await callback.message.answer(text=TEXT_ABOUT, reply_markup=await get_back_kb())
        await state.update_data(goals=[])
        await state.set_state(ProfileForm.about)
        return

    if text:
        if text in GOALS_LIST:
            if callback.message.text not in goals:
                goals.append(text)
                await state.update_data(goals=goals)
                await callback.message.edit_text(
                    f"Выбрана цель: {text}", reply_markup=None
                )
                await callback.message.answer(
                    text="Добавить еще цель?",
                    reply_markup=await get_confirmation_kb(with_back=True),
                )
                await state.set_state(ProfileForm.add_new_goal)
            else:
                await callback.message.answer(
                    "Вы уже выбрали эту цель. Теперь выберите другую:",
                    reply_markup=await get_goals_kb(with_back=True),
                )
        else:
            await callback.message.answer(text="Выбери цель из списка.")
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR, reply_markup=await get_goals_kb(with_back=True)
        )


@router.message(ProfileForm.add_new_goal)
@router.callback_query(ProfileForm.add_new_goal)
async def add_new_goal(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(
                event, "Добавить еще цель?", get_confirmation_kb, with_back=True
            )
            return
    else:
        callback = event

    await callback.answer()
    text = callback.data.split("_")[-1]

    await callback.message.delete()

    if text == CALLBACK_BACK:
        data = await state.get_data()
        goals = data["goals"]

        if goals:
            goals.pop()
            await state.update_data(goals=goals)

            if goals:
                await callback.message.answer(
                    text="Добавить еще цель?",
                    reply_markup=await get_confirmation_kb(with_back=True),
                )
                await state.set_state(ProfileForm.add_new_goal)
            else:
                await callback.message.answer(
                    text=TEXT_GOAL, reply_markup=await get_goals_kb(with_back=True)
                )
                await state.set_state(ProfileForm.goal)
        return

    if text:
        if text == "Да":
            await callback.message.answer(
                text=TEXT_GOAL, reply_markup=await get_goals_kb(with_back=True)
            )
            await state.set_state(ProfileForm.goal)
        elif text == "Нет":
            await callback.message.answer(
                text=TEXT_PHOTO, reply_markup=await get_photo_kb(with_back=True)
            )
            await state.set_state(ProfileForm.photo)
        else:
            await callback.message.answer(
                text=TEXT_WRONG_ANSWER,
                reply_markup=await get_confirmation_kb(with_back=True),
            )
            await state.set_state(ProfileForm.add_new_goal)
    else:
        await callback.message.answer(
            text=TEXT_ANSWER_TYPE_ERROR,
            reply_markup=await get_confirmation_kb(with_back=True),
        )
        await state.set_state(ProfileForm.add_new_goal)


@router.message(ProfileForm.photo)
async def save_photo(message: Message, state: FSMContext):
    if message.text in CMDS:
        await restrict_access(message, TEXT_PHOTO, get_photo_kb, with_back=True)
        return

    data = await state.get_data()
    if message.text == TEXT_BACK:
        await message.answer(
            text=TEXT_GOAL, reply_markup=await get_goals_kb(with_back=True)
        )
        await state.set_state(ProfileForm.goal)
        return

    # Проверяем, что это текст, а не несколько фото
    if message.text:
        if message.text == "Фото с профиля":
            photos = await message.bot.get_user_profile_photos(message.from_user.id)

            if photos.total_count > 0:
                photo = photos.photos[0][-1]
                file_id = photo.file_id
            else:
                file_id = None

            await state.update_data(photo=file_id)

        elif message.text == "Пропустить":
            await state.update_data(photo=None)
        else:
            await message.answer(
                TEXT_PHOTO_ERROR, reply_markup=await get_photo_kb(with_back=True)
            )
            return  # убрал повторную установку состояния

    # Обработка фото - проверяем количество
    elif message.photo:
        # Проверяем, является ли это частью альбома
        if message.media_group_id:
            if data.get("msg_group_id", "") != message.media_group_id:
                await message.answer(
                    TEXT_PHOTO_COUNT_ERROR,
                    reply_markup=await get_photo_kb(with_back=True),
                )
                await state.update_data(msg_group_id=message.media_group_id)
                return
            else:
                return

        # Берём самую большую версию фото
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)

    # Если пришел неподдерживаемый тип контента
    else:
        await message.answer(
            TEXT_PHOTO_ERROR, reply_markup=await get_photo_kb(with_back=True)
        )
        return  # убрал повторную установку состояния

    await check_profile(message=message, state=state)


async def check_profile(message: Message, state: FSMContext):
    data = await state.get_data()

    nickname = escape(data["nickname"])
    telegram_tag = escape(data["telegram_tag"]) if data["telegram_tag"] else "Нет"
    gender = escape(data["gender"]) if data["gender"] else "Нет"
    games = [escape(game) for game in data["games"]]
    about = escape(data["about"])
    goals = [escape(goal) for goal in data["goals"]]
    photo = data["photo"]
    time = [escape(t) for t in data["time"]]

    games_str = ", ".join(games)
    aion = data["games"].get("AION 2")
    if aion:
        games_str += (
            f"\nAION 2 — сервер: {escape(aion.get('server') or 'Не указан')}; "
            f"фракция: {escape(aion.get('faction') or 'Не указана')}; "
            f"ранг: {escape(aion.get('rank') or 'Не указан')}"
        )
    time_str = ", ".join(time)
    goals_str = ", ".join(goals)

    profile = PROFILE_SAMPLE.format(
        nickname=nickname,
        age=data.get("age") or "Не указан",
        telegram_tag=telegram_tag,
        gender=gender,
        game=games_str,
        about=about,
        time=time_str,
        goal=goals_str,
    )

    if photo:
        try:
            await message.answer_photo(photo=photo, caption=profile)
        except:
            await message.answer(text=profile + PHOTO_SAMPLE)
    else:
        await message.answer(text=profile + PHOTO_SAMPLE)

    await message.answer(
        text=IS_PROFILE_OK, reply_markup=await get_commit_profile_kb(with_back=False)
    )
    await state.set_state(ProfileForm.check_profile)


@router.message(ProfileForm.check_profile)
@router.callback_query(
    ProfileForm.check_profile,
    F.data.in_(["profile_correct", "profile_incorrect", "back_from_check"]),
)
async def commit_profile(event: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(event, IS_PROFILE_OK, get_commit_profile_kb)
            return
    else:
        callback = event

    await callback.message.delete()

    if callback.data == "back_from_check":
        await callback.message.answer(
            text=TEXT_PHOTO, reply_markup=await get_photo_kb(with_back=True)
        )
        await state.set_state(ProfileForm.photo)
        await callback.answer()
        return

    if not await repository.get_profile(user_id=callback.from_user.id):
        await save_profile(callback=callback, state=state)

    if callback.data == "profile_correct":
        await callback.message.answer(
            text=TEXT_SUCCESS, reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(ProfileForm.is_active)
        await callback.message.answer(
            text=TEXT_ALLOW_INVITATIONS,
            reply_markup=await get_status_kb(with_back=True),
        )
        await callback.answer()

    elif callback.data == "profile_incorrect":
        await callback.message.answer(text="Редактируем анкету...")
        await start_edit_profile_message(callback.message, state)
        await callback.answer()


@router.message(ProfileForm.is_active)
@router.callback_query(ProfileForm.is_active)
async def save_status(
    event: Union[CallbackQuery, Message], state: FSMContext, statistic: Statistic
):
    asyncio.create_task(statistic.set_filled_profile(event.from_user.id))
    if isinstance(event, Message):
        if event.text in CMDS:
            await restrict_access(
                event, TEXT_ALLOW_INVITATIONS, get_status_kb, with_back=True
            )
            return
    else:
        callback = event

    if callback.data == "back_from_status":
        await callback.message.answer(
            text=IS_PROFILE_OK, reply_markup=await get_commit_profile_kb(with_back=True)
        )
        await state.set_state(ProfileForm.check_profile)
        await callback.answer()
        return

    status = callback.data.split("_")[-1]
    if status == "true":
        await repository.activate_profile(user_id=callback.from_user.id)
    elif status == "false":
        await repository.deactivate_profile(user_id=callback.from_user.id)
    else:
        await callback.message.answer(text=TEXT_WRONG_ANSWER)
        await state.set_state(ProfileForm.is_active)
        return

    await callback.bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=None,
    )

    await callback.message.edit_text(
        text=TEXT_ALLOW_INVITATIONS + TEXT_ACCEPTED
        if status == "true"
        else TEXT_REJECTED
    )

    await state.clear()

    await cmd_menu(callback.message)


async def save_profile(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    await repository.create_profile(
        user_id=data["user_id"] if "user_id" in data else callback.from_user.id,
        nickname=data["nickname"],
        age=data.get("age"),
        games=data["games"],
        time=data["time"],
        about=data["about"],
        goals=data["goals"],
        is_active=data.get("is_activate", False),
        telegram_tag=data["telegram_tag"],
        gender=data["gender"],
        photo=data["photo"],
    )
