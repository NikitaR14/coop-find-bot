from typing import Callable, Any, Awaitable
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from utils.advertisment import POP_UPS
from repositories.user_repository import user_repository
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import random


class AdvertismentMiddleware(BaseMiddleware):
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any]
    ) -> Any:
        if isinstance(event, CallbackQuery):
            if users := await user_repository.get_user(user_id=event.from_user.id):
                user = users[0] #Костыль из-за стороннего разработчика
                if user.clicks + 1 == 10:
                    pop_up = random.randint(1, 10)
                    if user.last_pop_up == pop_up:
                        pop_up = pop_up + 1 if pop_up != 10 else pop_up - 1
                    ad = POP_UPS[pop_up]
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти", callback_data=f"go_to_{ad['link']}")]])
                    await event.bot.send_photo(
                        chat_id=event.from_user.id,
                        photo=ad["pic"],
                        caption=ad["text"],
                        reply_markup=kb,
                    )
                    await user_repository.update_clicks(user_id=event.from_user.id, clicks=0)
                    await user_repository.update_last_pop_up(user_id=event.from_user.id, pop_up=pop_up)
                else:
                    await user_repository.update_clicks(user_id=event.from_user.id, clicks=user.clicks + 1)

        return await handler(event, data)

        
        
