import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from supabase import create_client, Client

# ================= НАСТРОЙКИ =================
# 1. Токен бота из Nyxgram
BOT_TOKEN = "1780244500:ynwsVbg3UOT8ceBWXxShNAk9j9nqTr_E6ti"

# 2. API Nyxgram
NYX_API_BASE = "https://nyxgram.new.tg"

# 3. Данные из Supabase
SUPABASE_URL = "https://xktkhtxdmjibqlsbkpq.supabase.co" 
SUPABASE_KEY = "sb_publishable_6R6LPZooWoTfoyEm9BErgQ_8NnHCYzg"

# 4. ID админа (сначала 0, потом впишешь свой ID)
MAIN_ADMIN_ID = 0 

# Интервал проверки
CHECK_INTERVAL = 2.0
# ============================================

session = AiohttpSession(api=TelegramAPIServer.from_base(NYX_API_BASE))
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= БАЗА ДАННЫХ =================
def is_known(gift_id: str) -> bool:
    try:
        response = supabase.table("known_gifts").select("gift_id").eq("gift_id", gift_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Ошибка БД (is_known): {e}")
        return False

def mark_known(gift_id: str, name: str):
    try:
        supabase.table("known_gifts").insert({"gift_id": gift_id, "name": name}).execute()
    except Exception as e:
        print(f"Ошибка БД (mark_known): {e}")

# ================= ПАРСЕР =================
async def fetch_available_gifts() -> list:
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/getAvailableGifts"
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url, timeout=10) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    print(f"API Error: {data}")
                    return []
                return data.get("result", {}).get("gifts", [])
    except Exception as e:
        print(f"❌ Ошибка сети: {e}")
        return []

# ================= ОТПРАВКА =================
async def send_alert(gift: dict):
    gift_id = str(gift.get("id", "unknown"))
    name = gift.get("name", "Без названия")
    price = gift.get("price", "?")
    total_supply = gift.get("total_supply", "?")
    
    # Ссылка на подарок
    market_link = f"https://t.me/gift/{gift_id}" 
    
    sticker = gift.get("sticker", {})
    image_url = sticker.get("thumbnail", {}).get("file_id")

    text = f"""
⚡️ <b>НОВЫЙ ДРОП!</b> ⚡️

🎁 <b>Подарок:</b> <a href="{market_link}">{name}</a>
💸 <b>Цена:</b> <code>{price} ⭐</code>
📦 <b>Тираж:</b> <code>{total_supply} шт.</code>
🆔 <b>ID:</b> <code>{gift_id}</code>

🚀 <b>Хватай быстрее!</b>
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 КУПИТЬ", url=market_link)]
    ])

    if MAIN_ADMIN_ID != 0:
        try:
            if image_url:
                await bot.send_photo(chat_id=MAIN_ADMIN_ID, photo=image_url, caption=text, reply_markup=keyboard)
            else:
                await bot.send_message(chat_id=MAIN_ADMIN_ID, text=text, reply_markup=keyboard)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")
    else:
        print(f"🔥 Новый дроп: {name} ({gift_id})")

# ================= ЦИКЛ =================
async def monitor_market():
    print("🟢 Сканер NyxGram запущен...")
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
            print(f"❌ Ошибка цикла: {e}")
            await asyncio.sleep(10)

# ================= КОМАНДЫ =================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        f"👋 Привет, {message.from_user.full_name}!\n"
        f"🆔 Твой ID в NyxGram: <code>{message.from_user.id}</code>\n"
        f"👤 Юзернейм: @{message.from_user.username}\n\n"
        f"Скопируй ID и вставь его в код (MAIN_ADMIN_ID), чтобы получать уведомления."
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    try:
        response = supabase.table("known_gifts").select("*", count="exact").execute()
        count = response.count if response.count else 0
        await message.answer(f"🟢 Работаю.\n📦 В базе: {count} подарков.")
    except Exception as e:
        await message.answer(f"🟢 Работаю, но ошибка БД: {e}")

# ================= ЗАПУСК =================
async def main():
    asyncio.create_task(monitor_market())
    print("🤖 Бот запущен (Discloud mode).")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
