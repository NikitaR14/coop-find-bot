from html import escape
from handlers.menu import TEXT_INTRO
from keyboards.menu_kb import get_menu_keyboard
from utils.level_up import level_up
from statistic import Statistic
import asyncio
from keyboards.search_kb import get_invite_profile_kb, get_to_dialog_with_user_kb
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from utils.schedule_estimate import schedule_estimate
from handlers.search.search import TEXT_ADDITIONAL_INFO, TEXT_INVITE, TEXT_SENT_MESSAGE
from handlers.search.search import MESSAGE_TEXT, TEXT_SEND_MESSAGE
from aiogram import Router, F, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
from handlers.search.search import TEXT_GAMES
from keyboards.profile_kb import get_game_inline_kb, get_gallery_kb
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from repositories.profile_repository import profile_repository as pr
from statistic import Statistic
from utils.profile_templates import get_profile_template
from models.profile import Profile
import random



TEXT_END_AUTOFIT = """
Ой, кажется, я пока показал тебе всех подходящих тиммейтов
 
❤ Попробуй зайти позже — я найду для тебя новые анкеты 
"""

class Autofit(StatesGroup):
    waiting_for_game = State()

class AutofitProfiles(StatesGroup):
    waiting_for_answer = State()
    waiting_for_message = State()

def autofit_kb():
    kb = [
        [KeyboardButton(text="✅Да"),
         KeyboardButton(text="❌Нет"),],
        [KeyboardButton(text="Завершить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def gallery_kb(user_id: int, game: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Галерея📷", callback_data=f"autofit_gallery_{user_id}_{game}")]
        ])
    return kb

async def invite_user(message: Message, 
                      teammate_id: int, 
                      game: str, 
                      apscheduler: AsyncIOScheduler,
                      statistic: Statistic,
                      state: FSMContext):
    asyncio.create_task(statistic.set_invite_game(message.from_user.id))
    if message.from_user.username:
        postfix = TEXT_ADDITIONAL_INFO.format(tag="@" + message.from_user.username)

    user_profile = await pr.get_profile(user_id=message.from_user.id)
    profile = await pr.get_profile(user_id=teammate_id)

    keyboard = await get_invite_profile_kb(user_id=message.from_user.id) if user_profile else None
    await message.bot.send_message(
            chat_id=teammate_id,
            text=escape(TEXT_INVITE.format(name=message.from_user.full_name, game=game) + postfix),
            reply_markup=keyboard
        )
    await message.answer(text=TEXT_SENT_MESSAGE)

    if message.from_user.id not in profile.teammate_ids:
        dt = datetime.now() + timedelta(hours=24)
        await schedule_estimate(
                apscheduler=apscheduler,
                time=dt,
                bot=message.bot,
                user_id=message.from_user.id,
                teammate=profile.nickname,
                teammate_id=teammate_id,
                state=state
            )



router = Router()

@router.message(AutofitProfiles.waiting_for_message)
async def send_message(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправь текстовое сообщение")
        return
    try:
        data = await state.get_data()
        game = data.get("game")
        user_id = data.get("user_id")

        profile = await pr.get_profile(user_id=message.from_user.id)
        postfix = '\nТы можешь ответить ему в личных сообщениях, нажав кнопку “Ответить”👇' if message.from_user.id else ""
        try:
            await message.bot.send_message(
                    chat_id=user_id,
                    text=escape(MESSAGE_TEXT.format(nick=profile.nickname, game=game, text=message.text) + postfix),
                    reply_markup=await get_to_dialog_with_user_kb(
                        user_id=message.from_user.id)
                )
            await message.answer(text=TEXT_SENT_MESSAGE)
            await state.set_state(AutofitProfiles.waiting_for_answer)
        except Exception as e:
            print(e)
            await state.set_state(AutofitProfiles.waiting_for_answer)
            await message.answer("Произошла ошибка при отправке сообщения, попробуй снова")
        
        if profile:
            if not profile.send_first_message:
                new_xp = profile.experience + 20
                if profile.experience // 100 < new_xp // 100:
                    await level_up(message.bot, profile.user_id, new_xp // 100 + 1)
                await pr.add_experience(user_id=profile.user_id, experience=20)
                await pr.update_send_first_message(user_id=profile.user_id)
    except Exception as e:
        print(e)
        await state.set_state(AutofitProfiles.waiting_for_answer)
        await message.answer("Произошла ошибка, попробуй снова")

@router.callback_query(F.data == "autofit")
async def autofit_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()

    await callback.message.answer(text=TEXT_GAMES, reply_markup=await get_game_inline_kb(with_back=True))
    await state.set_state(Autofit.waiting_for_game)

@router.callback_query(Autofit.waiting_for_game)
async def autofit_game_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()

    game = callback.data.split("_")[-1]

    if game == "back":
        await callback.message.answer(text="Автоподбор отменен", reply_markup=ReplyKeyboardRemove())
        await callback.message.answer(text=TEXT_INTRO, reply_markup=await get_menu_keyboard())
        await state.set_state(None)
        return

    try:
        profiles = await pr.get_profiles_by_game(game=game, user_id=callback.from_user.id)
        # The legacy swipe-style autofit sends directly through aiogram.  The
        # regular search supports both platforms; keep autofit Telegram-only
        # until its whole state machine is moved to durable contact requests.
        profiles = [profile for profile in profiles if profile.platform == "telegram"]
        if not profiles:
            await state.set_state(None)
            await callback.message.answer("По этой игре нет доступных профилей...", reply_markup=ReplyKeyboardRemove())
            await callback.message.answer(text=TEXT_INTRO, reply_markup=await get_menu_keyboard())
            return

        profiles = random.sample(profiles, 10 if len(profiles) > 10 else len(profiles))

        await state.update_data(profiles=profiles, 
                                index=0,
                                game=game)

        await send_profile(callback.message, state)

    except Exception as e:
        print(e)
        await callback.message.answer("Произошла ошибка при получении профилей, попробуй снова")
        return
        
async def send_profile(message: Message, state: FSMContext):
    data = await state.get_data()
    profiles = data.get("profiles")
    index = data.get("index")
    game = data.get("game")

    if index >= len(profiles):
        await state.clear()
        await message.answer(TEXT_END_AUTOFIT, reply_markup=ReplyKeyboardRemove())
        return

    profile: Profile = profiles[index]
    profile_template = await get_profile_template(profile, game)

    profile_message_id = data.get("profile_message_id")
    action_message_id = data.get("action_message_id")
    gallery_message_id = data.get("gallery_message_id")
    

    if profile_message_id:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=profile_message_id)
        await state.update_data(profile_message_id=None)
    
    if action_message_id:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=action_message_id)
        await state.update_data(action_message_id=None)

    if gallery_message_id:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=gallery_message_id)
        await state.update_data(gallery_message_id=None)

    if profile.photo:
        try:
            msg = await message.answer_photo(photo=profile.photo, caption=profile_template, reply_markup=await gallery_kb(user_id=profile.user_id, game=game))
        except Exception as e:
            print(e)
            msg = await message.answer(text=profile_template, reply_markup=await gallery_kb(user_id=profile.user_id, game=game))
    else:
        msg = await message.answer(text=profile_template, reply_markup=await gallery_kb(user_id=profile.user_id, game=game))

    await state.update_data(profile_message_id=msg.message_id)

    act_msg = await message.answer("Выбери действие:", reply_markup=autofit_kb())
    await state.update_data(action_message_id=act_msg.message_id)

    await state.set_state(AutofitProfiles.waiting_for_answer)

@router.message(AutofitProfiles.waiting_for_answer)
async def answer_handler(message: Message, state: FSMContext, apscheduler: AsyncIOScheduler, statistic: Statistic):
    data = await state.get_data()

    try:
        if message.text == "✅Да":
            try:
                index = data.get("index")
                profiles = data.get("profiles")
                game = data.get("game")
                await invite_user(message=message,
                                game=game,
                                teammate_id=profiles[index].user_id,
                                apscheduler=apscheduler,
                                statistic=statistic,
                                state=state)
            except Exception as e:
                print(e)
                await message.answer("Произошла ошибка при приглашении пользователя, попробуй снова")
            
            index = data.get("index", 0) + 1
            await state.update_data(index=index)
            await send_profile(message, state)
        elif message.text == "❌Нет":
            index = data.get("index", 0) + 1
            await state.update_data(index=index)
            await send_profile(message, state)
        elif message.text == "Завершить":
            await state.clear()
            msg = await message.answer("Автоподбор завершен", reply_markup=ReplyKeyboardRemove())
            await msg.delete()
            await message.answer(text=TEXT_INTRO, reply_markup=await get_menu_keyboard())

        else:
            await message.answer("Пожалуйста, выбери действие с помощью кнопок ниже", reply_markup=autofit_kb())
    except Exception as e:
        print(e)
        await message.answer("Произошла ошибка, попробуй снова")
        await state.set_state(None)

@router.callback_query(F.data.startswith("autofit_gallery_"))
async def gallery_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    try:
        data = callback.data.split("_")
        user_id = int(data[-2])
        game = data[-1]

        profile = await pr.get_profile(user_id=user_id)
        
        media = []
        for game in profile.games:
            if game.name == game:
                media = [InputMediaPhoto(media=photo) for photo in game.gallery if game.gallery]
                break
        
        if not media:
            gallery_msg = await callback.message.answer(f"Упс, {escape(profile.nickname)} не прикрепил фото игрового профиля")
            await state.update_data(gallery_message_id=gallery_msg.message_id)
            return

        gallery_msg = await callback.message.answer_media_group(media=media, caption=escape(f"Галерея {profile.nickname} по игре {game}"))
        await state.update_data(gallery_message_id=gallery_msg.message_id)

    except Exception as e:
        print(e)
        await callback.message.answer("Произошла ошибка при загрузке галереи, попробуй снова")
