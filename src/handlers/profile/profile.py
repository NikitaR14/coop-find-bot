from email.mime import message

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InputMediaPhoto, FSInputFile
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards.profile_kb import *
from utils.constants import *
from repositories.profile_repository import profile_repository as repository
from services.platform_repository import platform_repository
from .create_profile import start_profile
from statistic import Statistic
from utils.profile_templates import get_profile_template, get_profile_template_no_rank
import asyncio
from html import escape
from pathlib import Path


router = Router()

class PhotoForm(StatesGroup):
    photo = State()

### ТЕКСТЫ
TEXT_INTRO = "Отлично! Что ты хочешь изменить в своей анкете?"
TEXT_DELETE_PROFILE = "Твоя анкета удалена. Я не плачу, это просто пиксели."
TEXT_NO_PROFILE = "У тебя еще нет анкеты.\nСоздай ее командой /profile"
TEXT_SEND_PHOTO = "Пришли новое фото профиля в чат."
TEXT_PHOTO_UPDATED = "Фото профиля обновлено."
TEXT_PHOTO_ERROR = 'Пришлите фотографию профиля!'
TEXT_PROFILE_DEACTIVATED = "Твоя анкета снята с поиска. Ты сможешь ее разместить в любой момент."
TEXT_PROFILE_ACTIVATED = "Твоя анкета успешно размещена. Теперь ее видят другие пользователи."
TEXT_YOUR_CHOICE = "Анкета {name}"
TEXT_GALLERY = """
✨ Галерея игрока «{name}».
Тут находится результат его игры: его лут, сила аккаунта, персонажи, соборки и многое другое.

Если галерея не соответствует игре, отправь скрин в поддержку: @ggstore_support
"""
TEXT_CONFIRM_DELETE_PROFILE = """
Ты точно хочешь удалить анкету? Я буду грустить 🥺
"""


@router.message(Command("profile"))
async def update_profile(message: Message):
    await message.delete()
    await message.answer(text=TEXT_INTRO, reply_markup=(await get_profile_kb(user_id=message.from_user.id)).as_markup())

@router.callback_query(F.data == "profile")
async def update_profile_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(text=TEXT_INTRO, reply_markup=(await get_profile_kb(user_id=callback.from_user.id)).as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("read_profile"))
async def read_profile(callback: CallbackQuery, state: FSMContext, statistic: Statistic):
    asyncio.create_task(statistic.set_open_profile(callback.from_user.id))

    await callback.answer()
    await callback.message.delete()

    callback_parts = callback.data.split("_")
    reference_id = int(callback_parts[-1])
    data = await state.get_data()

    is_shared_profile = "otherid" in callback_parts or "otheridfilter" in callback_parts
    if is_shared_profile:
        type_user = "other"
    elif "filter" in callback_parts:
        type_user = "other"
    else:
        type_user = callback_parts[-2]


    if type_user == "other":
        if "game" in data:
            game = data["game"]
        else:
            await callback.message.answer("Я потерял игру, по которой производится поиск. Попробуйте заново")
            return 
    

    if is_shared_profile:
        profile = await platform_repository.get_profile_by_id(reference_id)
    else:
        profile = await repository.get_profile(user_id=reference_id)

    if profile:

        if type_user == "other":
            keyboard = await get_interaction_kb(profile_id=profile.id, game=game, need_filter="filter" in callback.data)
        elif type_user == "invite":
            keyboard = await get_back_to_main_menu_from_invite(reference_id)
        else:
            keyboard = await get_back_to_menu()
            
        prefix = TEXT_YOUR_CHOICE.format(name=escape(profile.nickname)) if type_user == "other" else ""

        profile_text = prefix + await get_profile_template(profile, game) if type_user == "other" else prefix + await get_profile_template_no_rank(profile)

        if profile.photo:
            try:
                photo = profile.photo
                if profile.photo_origin in {"local", "discord"} and Path(profile.photo).is_file():
                    photo = FSInputFile(profile.photo)
                await callback.message.answer_photo(
                    photo=photo,
                    caption=profile_text,
                    reply_markup=keyboard)
                await callback.answer()
                return
            except:
                pass
        await callback.message.answer(
                    text=profile_text,
                    reply_markup=keyboard
                )

    else:
        await callback.message.answer(text=TEXT_NO_PROFILE, reply_markup=await get_back_to_menu())
    
    await callback.answer()


@router.callback_query(F.data.startswith("show_gallery_"))
async def show_gallery(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()

    parts = callback.data.split("_")
    reference_id = int(parts[-2])
    game = parts[-1]

    shared = "profile" in parts or "profilefilter" in parts
    profile = (
        await platform_repository.get_profile_by_id(reference_id)
        if shared else await repository.get_profile(user_id=reference_id)
    )
    if not profile:
        await callback.message.answer(TEXT_NO_PROFILE, reply_markup=await get_back_to_menu())
        return
    nickname = profile.nickname
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад",
        callback_data=(
            f"read_profile_otherid_{profile.id}"
            if "filter" not in callback.data
            else f"read_profile_otheridfilter_{profile.id}"
        )
    )]])


    games = profile.games if shared else await repository.get_games_by_user_id(user_id=reference_id)
    if games:
        games = {game.name: game for game in games}
        if game in games:
            if games[game].gallery:
                media = [InputMediaPhoto(media=file_id) for file_id in games[game].gallery]
                await callback.bot.send_media_group(chat_id=callback.message.chat.id, media=media)
                await callback.message.answer(escape(TEXT_GALLERY.format(name=nickname)), reply_markup=kb)
                return
    await callback.message.answer(f"Упс, {escape(nickname)} не прикрепил фото игрового профиля", reply_markup=kb)
    
@router.callback_query(F.data == "delete_profile")
async def delete_profile(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer(TEXT_CONFIRM_DELETE_PROFILE, reply_markup=await get_delete_confirm_kb())

async def delete_profile(callback: CallbackQuery):
    await callback.message.delete()
    await repository.delete_profile(user_id=callback.from_user.id)
    await callback.message.answer(text=TEXT_DELETE_PROFILE, reply_markup=await get_back_to_menu())
    await callback.answer()

@router.callback_query(F.data.startswith("delete_confirm_"))
async def delete_profile_confirm(callback: CallbackQuery):
    await callback.answer()

    response = callback.data.split("_")[-1]

    if response == "yes":
        await delete_profile(callback)
    else:
        await update_profile_callback(callback)



@router.callback_query(F.data.in_(["deactivate_profile", "activate_profile"]))
async def deactivate_profile(callback: CallbackQuery):
    await callback.message.delete()

    if await repository.get_profile(user_id=callback.from_user.id):
        if callback.data == "deactivate_profile":
            await repository.deactivate_profile(user_id=callback.from_user.id)
            await repository.update_self_deactivated(user_id=callback.from_user.id, value=True)
            await callback.message.answer(text=TEXT_PROFILE_DEACTIVATED, reply_markup=await get_back_to_menu())
        else:
            await repository.activate_profile(user_id=callback.from_user.id)
            await repository.update_self_deactivated(user_id=callback.from_user.id, value=None)
            await callback.message.answer(text=TEXT_PROFILE_ACTIVATED, reply_markup=await get_back_to_menu())

    else:
        await callback.message.answer(text=TEXT_NO_PROFILE, reply_markup=await get_back_to_menu())

    await callback.answer()

TEXT_SUCCESS_ACTIVATE = """
Ура! Твоя анкета снова активирована. Теперь тебя снова видят и
могут приглашать 🎉

Удачи в поиске тиммейтов 😌
"""


@router.callback_query(F.data == "activate_inactive_profile")
async def activate_inactive_profile(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()

    if await repository.get_profile(user_id=callback.from_user.id):
        await repository.activate_profile(user_id=callback.from_user.id)
        await repository.update_self_deactivated(user_id=callback.from_user.id, value=None)
        await callback.message.answer(text=TEXT_SUCCESS_ACTIVATE)
        from handlers.menu import TEXT_INTRO as menu_text, get_menu_keyboard
        await callback.message.answer(text=menu_text, reply_markup=await get_menu_keyboard())

    else:
        await callback.message.answer(text=TEXT_NO_PROFILE, reply_markup=await get_back_to_menu())
