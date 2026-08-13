import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram import types
from config import settings
import logging
from handlers import routers
from middlewares.middleware import SubscriptionMiddleware
from middlewares.apscheduler_middleware import SchedulerMiddleware
from middlewares.actions_middleware import ActivityTrackingMiddleware
from middlewares.ad_middleware import AdvertismentMiddleware
from middlewares.album_middleware import AlbumMiddleware
from middlewares.inactive_middleware import InactiveMiddleware
from middlewares.utm_middleware import UtmTrackingMiddleware
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from google_sheet import GoogleSheetService
from statistic import Statistic
from repositories.user_repository import user_repository
from utils.schedule_activity import deactivate_inactive_profiles, send_message_to_inactive_profiles
from aiogram.filters.command import Command
import asyncio


logging.basicConfig(level=logging.INFO)

dp = Dispatcher()


# @dp.message(F.photo)
# async def handle_media(message: Message):
#     if message.chat.id == settings.PRIVATE_PHOTO_GROUP_ID:
#         await message.reply(message.photo[-1].file_id)
        
@dp.callback_query(F.data.startswith("go_to_"))
async def handle_go_to_callback(callback: types.CallbackQuery, statistic: Statistic):
    asyncio.create_task(statistic.set_go_website(callback.from_user.id))
    await callback.answer()
    url = callback.data.removeprefix("go_to_")

    await callback.message.edit_reply_markup()
    await callback.message.answer(f"Переходи 👉 {url}")

# Run the bot
async def main() -> None:
    session = AiohttpSession(proxy=settings.TELEGRAM_PROXY_URL) if settings.TELEGRAM_PROXY_URL else None
    bot = Bot(
        token=settings.TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    google_sheet = GoogleSheetService(credentials_path=settings.GOOGLE_SHEET_CREDENTIALS_PATH,
                                      sheet_id=settings.GOOGLE_SHEET_ID,
                                      worksheet=settings.GOOGLE_SHEET_WORKSHEET_NAME)
    statistic = Statistic(google_sheet=google_sheet,
                          user_repository=user_repository)
    dp['statistic'] = statistic

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    
    for router in routers:
        dp.include_router(router)

    scheduler_middleware = SchedulerMiddleware(scheduler=scheduler)
    #sub_middleware = SubscriptionMiddleware()
    action_middleware = ActivityTrackingMiddleware()
    album_middleware = AlbumMiddleware()
    ad_middleware = AdvertismentMiddleware()
    inactive_middleware = InactiveMiddleware()
    utm_middleware = UtmTrackingMiddleware()

    #dp.message.middleware(sub_middleware)
    #dp.callback_query.middleware(sub_middleware)
    dp.callback_query.middleware(ad_middleware)

    dp.message.middleware(scheduler_middleware)
    dp.callback_query.middleware(scheduler_middleware)
    
    dp.message.middleware(album_middleware)
    dp.callback_query.middleware(album_middleware)
    
    dp.message.middleware(action_middleware)
    dp.callback_query.middleware(action_middleware)
    
    dp.message.middleware(inactive_middleware)
    dp.callback_query.middleware(inactive_middleware)

    if settings.ENABLE_UTM_MIDDLEWARE:
        dp.message.middleware(utm_middleware)
        dp.callback_query.middleware(utm_middleware)

    scheduler.start()
    
    scheduler.add_job(
         deactivate_inactive_profiles, "interval", hours=24, args=[bot]
    )
    scheduler.add_job(
       send_message_to_inactive_profiles, "interval",  hours=24, args=[bot]
    )


    await dp.start_polling(bot)

    
    

if __name__ == "__main__":
    asyncio.run(main())
          
