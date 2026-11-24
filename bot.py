import asyncio
import aiosqlite
import aiohttp
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "1780244500:ynwsVbg3UOT8ceBWXxShNAk9j9nqTr_E6ti"
MAIN_ADMIN_ID = 0  # Впиши свой ID после первого /start
MAIN_ADMIN_USERNAME = "inoagent"
CHECK_INTERVAL = 1.0
NYX_API_BASE = "https://nyxgram.new.tg"
DB_PATH = "nyx_gifts.db"

# Koyeb передаёт порт через переменную окружения PORT
PORT = int(os.environ.get("PORT", 8000))
# ============================================

session = AiohttpSession(api=TelegramAPIServer.from_base(NYX_API_BASE))
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS known_gifts (
                gift_id TEXT PRIMARY KEY,
                name TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == MAIN_ADMIN_ID:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def add_admin(user_id: int, username: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins (user_id, username, added_by) VALUES (?, ?, ?)",
            (user_id, username, added_by)
        )
        await db.commit()

async def remove_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()

# ================= ПАРСЕР =================
async def fetch_available_gifts() -> list:
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/getAvailableGifts"
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url, timeout=5) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    return []
                return data.get("result", {}).get("gifts", [])
    except Exception as e:
        print(f"❌ Ошибка сети: {e}")
        return []

# ================= ОТПРАВКА УВЕДОМЛЕНИЙ =================
async def send_alert(gift: dict):
    gift_id = str(gift.get("id", "unknown"))
    name = gift.get("name", "Без названия")
    price = gift.get("price", "?")
    total_supply = gift.get("total_supply", "?")
    market_link = f"{NYX_API_BASE}/gift/{gift_id}"
    sticker = gift.get("sticker", {})
    image_url = sticker.get("thumbnail", {}).get("file_id")

    text = f"""
⚡️ <b>ВНИМАНИЕ! НОВЫЙ ДРОП В NYXGRAM!</b> ⚡️

🎁 <b>Подарок:</b> <a href="{market_link}">{name}</a>
💸 <b>Цена:</b> <code>{price} ⭐</code>
📦 <b>Тираж:</b> <code>{total_supply} шт.</code>
🆔 <b>ID:</b> <code>{gift_id}</code>

🚀 <b>ДЕЙСТВУЙ БЫСТРО!</b>
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 КУПИТЬ СЕЙЧАС", url=market_link)]
    ])

    recipients = [MAIN_ADMIN_ID]
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM admins")
        rows = await cursor.fetchall()
        recipients.extend([row[0] for row in rows])

    for chat_id in set(recipients):
        if chat_id == 0:
            continue
        try:
            if image_url:
                await bot.send_photo(chat_id=chat_id, photo=image_url, caption=text, reply_markup=keyboard)
            else:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        except Exception as e:
            print(f"Ошибка отправки {chat_id}: {e}")

# ================= ФОНОВЫЙ ЦИКЛ =================
async def monitor_market():
    print("🟢 Сканер NyxGram запущен...")
    while True:
        try:
            gifts = await fetch_available_gifts()
            for gift in gifts:
                gift_id = str(gift.get("id"))
                async with aiosqlite.connect(DB_PATH) as db:
                    cursor = await db.execute("SELECT 1 FROM known_gifts WHERE gift_id = ?", (gift_id,))
                    if await cursor.fetchone() is None:
                        await db.execute("INSERT INTO known_gifts (gift_id, name) VALUES (?, ?)", (gift_id, gift.get("name", "Unknown")))
                        await db.commit()
                        print(f"🔥 Новый дроп: {gift.get('name')}")
                        await send_alert(gift)
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"❌ Ошибка цикла: {e}")
            await asyncio.sleep(5)

# ================= HTTP HEALTH CHECK ДЛЯ KOYEB =================
async def health_handler(request):
    return web.Response(text="OK", status=200)

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/healthz", health_handler)  # Koyeb будет стучаться сюда
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Health check сервер на порту {PORT}")

# ================= КОМАНДЫ =================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "без_юзернейма"

    info = (
        f"👋 Привет, <b>{message.from_user.full_name}</b>!\n\n"
        f"🆔 <b>Твой ID в NyxGram:</b> <code>{user_id}</code>\n"
        f"👤 <b>Юзернейм:</b> @{username}\n\n"
    )

    if await is_admin(user_id):
        info += (
            "✅ <b>У тебя есть доступ к боту.</b>\n\n"
            "📋 <b>Команды:</b>\n"
            "/status — статус\n"
            "/stats — статистика\n"
            "/clear — очистить базу\n"
        )
        if user_id == MAIN_ADMIN_ID or username == MAIN_ADMIN_USERNAME:
            info += (
                "\n👑 <b>Главный Админ</b>\n"
                "/a <id> — выдать админку\n"
                "/d <id> — забрать админку\n"
                "/admins — список админов\n"
            )
    else:
        info += (
            "⛔️ <b>Нет доступа.</b>\n\n"
            f"Скопируй ID <code>{user_id}</code> и отправь <b>@inoagent</b>, "
            f"чтобы он выдал доступ командой <code>/a {user_id}</code>."
        )
    await message.answer(info)

@dp.message(Command("a"))
async def cmd_add_admin(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID and (message.from_user.username or "").lower() != MAIN_ADMIN_USERNAME:
        await message.answer("⛔️ Только Главный Админ (@inoagent) может выдавать админку.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: <code>/a 123456789</code>")
        return
    try:
        new_admin_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return
    if new_admin_id == MAIN_ADMIN_ID:
        await message.answer("👑 Это и так Главный Админ.")
        return
    await add_admin(new_admin_id, "unknown", message.from_user.id)
    await message.answer(f"✅ Пользователь <code>{new_admin_id}</code> теперь админ.")
    try:
        await bot.send_message(new_admin_id, "🎉 Тебе выдали доступ! Напиши /start.")
    except Exception:
        pass

@dp.message(Command("d"))
async def cmd_remove_admin(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID and (message.from_user.username or "").lower() != MAIN_ADMIN_USERNAME:
        await message.answer("⛔️ Только Главный Админ (@inoagent) может забирать админку.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: <code>/d 123456789</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return
    await remove_admin(target_id)
    await message.answer(f"🗑 Админка у <code>{target_id}</code> забрана.")

@dp.message(Command("admins"))
async def cmd_list_admins(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id, username FROM admins ORDER BY added_at")
        rows = await cursor.fetchall()
    text = f"👑 <b>Главный Админ:</b> <code>{MAIN_ADMIN_ID}</code> (@{MAIN_ADMIN_USERNAME})\n\n"
    if rows:
        text += "📋 <b>Доп. админы:</b>\n"
        for uid, uname in rows:
            text += f"• <code>{uid}</code> (@{uname})\n"
    else:
        text += "📋 <i>Доп. админов нет.</i>"
    await message.answer(text)

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа.")
        return
    await message.answer(f"🟢 Работаю.\nИнтервал: <code>{CHECK_INTERVAL} сек.</code>")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM known_gifts")
        count = (await cursor.fetchone())[0]
    await message.answer(f"📦 В базе: <b>{count}</b> подарков.")

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM known_gifts")
        await db.commit()
    await message.answer("🗑 База подарков очищена.")

# ================= ЗАПУСК =================
async def main():
    await init_db()
    # Запускаем HTTP-сервер для Koyeb (health check)
    asyncio.create_task(start_health_server())
    # Запускаем сканер рынка
    asyncio.create_task(monitor_market())
    print("🤖 Бот запущен в NyxGram (Koyeb mode).")
    print(f"👑 Главный админ: @{MAIN_ADMIN_USERNAME} (ID={MAIN_ADMIN_ID})")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())