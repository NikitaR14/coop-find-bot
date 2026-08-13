from aiogram import Router, Bot, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from keyboards.clan_kb import *
from keyboards.profile_kb import (
    get_game_kb,
    get_raven_servers_kb,
    get_lineage_servers_pt_1,
    get_raven_clusters_kb,
)
from utils.constants import *
from repositories.clan_repository import clan_repository as repository
from utils.decorators import require_profile
from states.edit_clan import *
from states.create_clan import *
from keyboards.profile_kb import get_skip_keyboard
from handlers.clan.create_clan import TEXT_GAME
from typing import Union


router = Router()


### ТЕКСТЫ
TEXT_CHOOSE_FIELD = "Выбери поле, которое хочешь изменить:"
TEXT_EDIT_NAME = "Введи название клана."
TEXT_EDIT_GAME = "Выбери игру, в которую ищешь тиммейтов:"
TEXT_EDIT_DESCRIPTION = "Введи описание клана."
TEXT_EDIT_DEMANDS = "Введи требования для участия в клане."
TEXT_EDIT_PHOTO = "Отправь аватарку клана."
TEXT_ANSWER_TYPE_ERROR = "Ответь текстом."
TEXT_WRONG_ANSWER = "Выберите ответ из предложенного списка!"
TEXT_PHOTO_ERROR = 'Пришлите либо фотографию профиля, либо напишите "Пропустите"'
TEXT_REPEAT_PROFILE = "Заполни заново анкету своего клана"
TEXT_ACCEPTED = "\n\nПодтвеждено ✅"
TEXT_REJECTED = "\n\nОтклонено ❌"
IS_CLAN_OK = "Все верно?"
TEXT_SUCCESS = (
    "Отлично! Анкета твоего клана успешно создана и теперь доступна другим игрокам. 👾"
)
TEXT_SUCCESS_EDIT = "Изменения успешно сохранены! ✅"
TEXT_PHOTO_COUNT_ERROR = "Пришлите 1 фотографию"
MMO_GAMES = {"Warcraft", "WoR", "AION 2"}


@router.callback_query(F.data.startswith("edit_clan"))
async def start_edit_clan(callback: CallbackQuery, state: FSMContext):
    clan_id = int(callback.data.split("_")[-1])
    await callback.message.delete()

    await state.update_data(clan_id=clan_id)

    clan = await repository.get_clan_by_id(clan_id)

    await state.update_data(game=clan.game)
    if clan.game in ("Raven 2", "Lineage 2M") or clan.game in MMO_GAMES:
        markup = await get_edit_clan_fields_kb(clan_id, add_info=True)
    else:
        markup = await get_edit_clan_fields_kb(clan_id)

    await callback.message.answer(TEXT_CHOOSE_FIELD, reply_markup=markup)
    await state.set_state(EditClanForm.choose_field)
    await callback.answer()


async def start_edit_clan_message(message: Message, state: FSMContext):
    data = await state.get_data()
    clan_id = data["clan_id"]

    await message.answer(
        TEXT_CHOOSE_FIELD, reply_markup=await get_edit_clan_fields_kb(clan_id)
    )
    await state.set_state(EditClanForm.choose_field)


@router.callback_query(EditClanForm.choose_field)
async def process_field_selection(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[-1]

    await callback.answer()
    await callback.message.delete()

    data = await state.get_data()

    if field == "name":
        await callback.message.answer(TEXT_EDIT_NAME)
        await state.set_state(EditClanForm.name)

    elif field == "game":
        await callback.message.answer(
            TEXT_EDIT_GAME, reply_markup=await get_game_kb(with_back=False)
        )
        await state.set_state(EditClanForm.game)

    elif field == "desc":
        await callback.message.answer(TEXT_EDIT_DESCRIPTION)
        await state.set_state(EditClanForm.description)

    elif field == "demands":
        await callback.message.answer(TEXT_EDIT_DEMANDS)
        await state.set_state(EditClanForm.demands)

    elif field == "photo":
        await callback.message.answer(
            TEXT_EDIT_PHOTO, reply_markup=await get_skip_keyboard(with_back=False)
        )
        await state.set_state(EditClanForm.photo)

    elif field == "info":
        data = await state.get_data()
        clan_id = data["clan_id"]
        clan = await repository.get_clan_by_id(clan_id)
        game = clan.game

        if game == "Raven 2":
            from utils.raven import CLUSTER_TEXT

            await callback.message.answer(
                text=CLUSTER_TEXT,
                reply_markup=await get_raven_clusters_kb(with_back=True),
            )
            await state.set_state(EditClanForm.raven_cluster)
            return

        if game == "Lineage 2M":
            from utils.lineage import SERVER_TEXT

            await callback.message.answer(
                text=SERVER_TEXT,
                reply_markup=await get_lineage_servers_pt_1(with_back=True),
            )
            await state.set_state(EditClanForm.lineage_server)
            return

        if game in MMO_GAMES:
            await state.update_data(game=game)
            await callback.message.answer("Введите название сервера:")
            await state.set_state(EditClanForm.mmo_server)
            return

        await callback.message.answer(
            text="У этой игры нет дополнительной информации.",
            reply_markup=await get_back_to_menu(clan_id=clan_id),
        )
        await state.clear()
        return


@router.message(EditClanForm.name)
async def save_name(message: Message, state: FSMContext):
    data = await state.get_data()
    clan_id = data["clan_id"]

    if message.text:
        await repository.update_name(clan_id=clan_id, name=message.text)
        await message.answer(
            text=TEXT_SUCCESS_EDIT, reply_markup=await get_back_to_menu(clan_id=clan_id)
        )
        await state.clear()
    else:
        await message.answer(text=TEXT_ANSWER_TYPE_ERROR)
        await state.set_state(EditClanForm.name)


@router.callback_query(EditClanForm.game)
async def save_game(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    clan_id = data["clan_id"]
    await callback.answer()

    game = callback.data.split("_")[-1]

    await callback.message.edit_text(text=f"Выбрана игра: {game}", reply_markup=None)

    if game:
        if game in GAME_LIST:
            await state.update_data(game=game)
            if game == "Raven 2":
                from utils.raven import SERVER_TEXT

                await callback.message.answer(
                    text=SERVER_TEXT,
                    reply_markup=await get_raven_servers_kb(with_back=True),
                )
                await state.set_state(EditClanForm.raven_server)
            elif game == "Lineage 2M":
                from utils.lineage import SERVER_TEXT

                await callback.message.answer(
                    text=SERVER_TEXT,
                    reply_markup=await get_lineage_servers_pt_1(with_back=True),
                )
                await state.set_state(EditClanForm.lineage_server)
            elif game in MMO_GAMES:
                await callback.message.answer("Введите название сервера:")
                await state.set_state(EditClanForm.mmo_server)
            else:
                await repository.update_game(clan_id=clan_id, game=game)
                await callback.message.answer(
                    text=TEXT_SUCCESS_EDIT,
                    reply_markup=await get_back_to_menu(clan_id=clan_id),
                )
                await state.clear()
                return

        else:
            await callback.message.answer(text=TEXT_WRONG_ANSWER)
            await state.set_state(EditClanForm.game)
    else:
        await callback.message.answer(text=TEXT_ANSWER_TYPE_ERROR)
        await state.set_state(ClanForm.game)


@router.message(EditClanForm.mmo_server)
async def edit_mmo_server(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(TEXT_ANSWER_TYPE_ERROR)
        return
    await state.update_data(server=message.text.strip())
    data = await state.get_data()
    if data.get("game") == "AION 2":
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=value, callback_data=f"edit_mmo_faction_{value}"
                    )
                ]
                for value in AION_2_FACTIONS
            ]
        )
        await message.answer("Выберите фракцию клана:", reply_markup=markup)
    else:
        await message.answer("Введите фракцию клана:")
    await state.set_state(EditClanForm.mmo_faction)


@router.message(EditClanForm.mmo_faction)
@router.callback_query(EditClanForm.mmo_faction, F.data.startswith("edit_mmo_faction_"))
async def edit_mmo_faction(event: Union[Message, CallbackQuery], state: FSMContext):
    data = await state.get_data()
    if isinstance(event, CallbackQuery):
        faction = event.data.removeprefix("edit_mmo_faction_")
        message = event.message
        await event.answer()
    else:
        if not event.text:
            await event.answer(TEXT_ANSWER_TYPE_ERROR)
            return
        faction = event.text.strip()
        message = event
    await repository.update_mmo_info(
        data["clan_id"], server=data["server"], faction=faction, game=data.get("game")
    )
    await message.answer(
        text=TEXT_SUCCESS_EDIT,
        reply_markup=await get_back_to_menu(clan_id=data["clan_id"]),
    )
    await state.clear()


@router.callback_query(EditClanForm.raven_cluster)
async def edit_raven_cluster_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    clan_id = data.get("clan_id")

    cluster = callback.data.split("_")[-1]

    if cluster == "back":
        await callback.message.delete()
        await callback.message.answer(
            TEXT_CHOOSE_FIELD,
            reply_markup=await get_edit_clan_fields_kb(clan_id, add_info=True),
        )
        await state.set_state(EditClanForm.choose_field)
        return

    await state.update_data(raven_cluster=cluster)
    await callback.message.edit_text(
        text=f"Выбран кластер: {cluster}", reply_markup=None
    )

    from utils.raven import SERVER_TEXT

    await callback.message.answer(
        text=SERVER_TEXT, reply_markup=await get_raven_servers_kb(with_back=True)
    )
    await state.set_state(EditClanForm.raven_server)


@router.callback_query(EditClanForm.raven_server)
async def raven_server_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    clan_id = data["clan_id"]

    server = callback.data.split("_")[-1]
    cluster = data.get("raven_cluster")

    if server == "back":
        from utils.raven import CLUSTER_TEXT

        await callback.message.answer(
            text=CLUSTER_TEXT, reply_markup=await get_raven_clusters_kb(with_back=True)
        )
        await state.set_state(EditClanForm.raven_cluster)
        return

    await callback.message.edit_text(text=f"Выбран сервер: {server}", reply_markup=None)

    await repository.update_add_info(clan_id=clan_id, add_info=f"{cluster}@{server}")
    await callback.message.answer(
        text=TEXT_SUCCESS_EDIT, reply_markup=await get_back_to_menu(clan_id=clan_id)
    )
    await state.clear()
    return


@router.callback_query(EditClanForm.lineage_server)
async def lineage_server_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    clan_id = data["clan_id"]
    server = callback.data.split("_")[-1]

    if server == "back":
        await callback.message.delete()
        await callback.message.answer(
            TEXT_CHOOSE_FIELD,
            reply_markup=await get_edit_clan_fields_kb(clan_id, add_info=True),
        )
        await state.set_state(EditClanForm.choose_field)
        return

    await callback.message.edit_text(text=f"Выбран сервер: {server}", reply_markup=None)

    await repository.update_add_info(clan_id=clan_id, add_info=server)
    await callback.message.answer(
        text=TEXT_SUCCESS_EDIT, reply_markup=await get_back_to_menu(clan_id=clan_id)
    )
    await state.clear()
    return


@router.message(EditClanForm.description)
async def save_description(message: Message, state: FSMContext):
    data = await state.get_data()
    clan_id = data["clan_id"]

    if message.text:
        await repository.update_description(clan_id=clan_id, desc=message.text)
        await message.answer(
            text=TEXT_SUCCESS_EDIT, reply_markup=await get_back_to_menu(clan_id=clan_id)
        )
        await state.clear()

    else:
        await message.answer(text=TEXT_ANSWER_TYPE_ERROR)
        await state.set_state(EditClanForm.description)


@router.message(EditClanForm.demands)
async def save_demands(message: Message, state: FSMContext):
    data = await state.get_data()
    clan_id = data["clan_id"]

    if message.text:
        await repository.update_demands(clan_id=clan_id, demands=message.text)
        await message.answer(
            text=TEXT_SUCCESS_EDIT, reply_markup=await get_back_to_menu(clan_id=clan_id)
        )
        await state.clear()

    else:
        await message.answer(text=TEXT_ANSWER_TYPE_ERROR)
        await state.set_state(EditClanForm.demands)


@router.message(EditClanForm.photo)
async def save_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    clan_id = data["clan_id"]

    if message.photo:
        # Проверяем, является ли это частью альбома
        if message.media_group_id:
            if data.get("msg_group_id", "") != message.media_group_id:
                await message.answer(TEXT_PHOTO_COUNT_ERROR)
                await state.update_data(msg_group_id=message.media_group_id)
                return
            else:
                return

        # Берём самую большую версию фото
        file_id = message.photo[-1].file_id
        await repository.update_clan_photo(clan_id=clan_id, new_photo=file_id)
        await message.answer(text=TEXT_SUCCESS_EDIT, reply_markup=ReplyKeyboardRemove())
        await message.answer(
            "Назад к настройкам клана:",
            reply_markup=await get_back_to_menu(clan_id=clan_id),
        )
        await state.clear()

    elif message.text == "Пропустить":
        await repository.update_clan_photo(clan_id=clan_id, new_photo=None)
        await message.answer(text=TEXT_SUCCESS_EDIT, reply_markup=ReplyKeyboardRemove())
        await message.answer(
            "Назад к настройкам клана:",
            reply_markup=await get_back_to_menu(clan_id=clan_id),
        )
        await state.clear()

    else:
        await message.answer(text=TEXT_PHOTO_ERROR)
        await state.set_state(EditClanForm.photo)
        return
