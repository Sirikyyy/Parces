import asyncio
import aiohttp
import requests
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "1780244500:ynwsVbg3UOT8ceBWXxShNAk9j9nqTr_E6ti"
NYX_API_BASE = "https://nyxgram.new.tg"

SUPABASE_URL = "https://xktkhtxdmjibqlsbkpq.supabase.co" 
SUPABASE_KEY = "sb_publishable_6R6LPZooWoTfoyEm9BErgQ_8NnHCYzg"

MAIN_ADMIN_ID = 1780243908
CHECK_INTERVAL = 2.0
# ============================================

# Flask для Render (Health Check)
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running", 200

# Настройка Aiogram
session = AiohttpSession(api=TelegramAPIServer.from_base(NYX_API_BASE))
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Заголовки для Supabase (используем requests, как просил)
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def is_known(gift_id: str) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/known_gifts?gift_id=eq.{gift_id}&select=gift_id"
    try:
        resp = requests.get(url, headers=SUPABASE_HEADERS, timeout=5)
        return len(resp.json()) > 0
    except Exception as e:
        print(f"Ошибка БД (is_known): {e}")
        return False

def mark_known(gift_id: str, name: str):
    url = f"{SUPABASE_URL}/rest/v1/known_gifts"
    data = {"gift_id": gift_id, "name": name}
    try:
        requests.post(url, headers=SUPABASE_HEADERS, json=data, timeout=5)
    except Exception as e:
        print(f"Ошибка БД (mark_known): {e}")

async def fetch_available_gifts() -> list:
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/getAvailableGifts"
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url, timeout=10) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    return []
                return data.get("result", {}).get("gifts", [])
    except Exception as e:
        print(f"❌ Ошибка сети: {e}")
        return []

async def send_alert(gift: dict):
    gift_id = str(gift.get("id", "unknown"))
    name = gift.get("name", "Без названия")
    price = gift.get("price", "?")
    total_supply = gift.get("total_supply", "?")
    market_link = f"https://t.me/gift/{gift_id}" 
    
    sticker = gift.get("sticker", {})
    image_url = sticker.get("thumbnail", {}).get("file_id")

    text = f"⚡️ <b>НОВЫЙ ДРОП!</b> ⚡️\n\n🎁 <b>Подарок:</b> <a href='{market_link}'>{name}</a>\n💸 <b>Цена:</b> <code>{price} ⭐</code>\n📦 <b>Тираж:</b> <code>{total_supply} шт.</code>"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛒 КУПИТЬ", url=market_link)]])

    if MAIN_ADMIN_ID != 0:
        try:
            if image_url:
                await bot.send_photo(chat_id=MAIN_ADMIN_ID, photo=image_url, caption=text, reply_markup=keyboard)
            else:
                await bot.send_message(chat_id=MAIN_ADMIN_ID, text=text, reply_markup=keyboard)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

async def monitor_market():
    print("🟢 Сканер запущен...")
    while True:
        try:
            gifts = await fetch_available_gifts()
            for gift in gifts:
                gift_id = str(gift.get("id"))
                if not is_known(gift_id):
                    mark_known(gift_id, gift.get("name", "Unknown"))
                    await send_alert(gift)
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            await asyncio.sleep(10)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"👋 Привет, {message.from_user.full_name}!\n🆔 Твой ID: <code>{message.from_user.id}</code>\nСкопируй и вставь в MAIN_ADMIN_ID.")

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(monitor_market())
    loop.run_until_complete(dp.start_polling(bot))

if __name__ == "__main__":
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask для Render
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
