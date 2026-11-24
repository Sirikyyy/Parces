import time
import requests
import threading
import os
from flask import Flask

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "1780244500:ynwsVbg3UOT8ceBWXxShNAk9j9nqTr_E6ti"
NYX_API_BASE = "https://nyxgram.new.tg"

SUPABASE_URL = "https://xktkhtxdmjibqlsbkpq.supabase.co" 
SUPABASE_KEY = "sb_publishable_6R6LPZooWoTfoyEm9BErgQ_8NnHCYzg"

MAIN_ADMIN_ID = 1780243908  # Твой ID
CHECK_INTERVAL = 2.0
# ============================================

app = Flask(__name__)

@app.route('/')
def health():
    return "Gift Scanner is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Supabase ---
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

# Проверка, является ли юзер админом (главным или из базы)
def is_admin(user_id):
    if user_id == MAIN_ADMIN_ID:
        return True
    try:
        url = f"{SUPABASE_URL}/rest/v1/admins?user_id=eq.{user_id}&select=user_id"
        resp = requests.get(url, headers=SUPABASE_HEADERS, timeout=5)
        return len(resp.json()) > 0
    except:
        return False

# Выдать админку
def add_admin(user_id, username):
    url = f"{SUPABASE_URL}/rest/v1/admins"
    data = {"user_id": user_id, "username": username}
    requests.post(url, headers=SUPABASE_HEADERS, json=data, timeout=5)

# Забрать админку
def remove_admin(user_id):
    url = f"{SUPABASE_URL}/rest/v1/admins?user_id=eq.{user_id}"
    requests.delete(url, headers=SUPABASE_HEADERS, timeout=5)

# --- Работа с подарками ---
def is_known(gift_id):
    url = f"{SUPABASE_URL}/rest/v1/known_gifts?gift_id=eq.{gift_id}&select=gift_id"
    try:
        resp = requests.get(url, headers=SUPABASE_HEADERS, timeout=5)
        return len(resp.json()) > 0
    except:
        return False

def mark_known(gift_id, name):
    url = f"{SUPABASE_URL}/rest/v1/known_gifts"
    data = {"gift_id": gift_id, "name": name}
    requests.post(url, headers=SUPABASE_HEADERS, json=data, timeout=5)

# --- Логика бота ---
def get_updates(offset=None):
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        resp = requests.get(url, params=params, timeout=40)
        return resp.json()
    except:
        return {"ok": False}

def send_message(chat_id, text):
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def fetch_available_gifts():
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/getAvailableGifts"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if not data.get("ok"):
            return []
        return data.get("result", {}).get("gifts", [])
    except:
        return []

def send_alert_to_admins(gift):
    gift_id = str(gift.get("id", "unknown"))
    name = gift.get("name", "Без названия")
    price = gift.get("price", "?")
    total_supply = gift.get("total_supply", "?")
    market_link = f"https://t.me/gift/{gift_id}"
    
    text = f"⚡️ <b>НОВЫЙ ДРОП!</b> ⚡️\n\n🎁 <b>Подарок:</b> <a href='{market_link}'>{name}</a>\n💸 <b>Цена:</b> <code>{price} ⭐</code>\n📦 <b>Тираж:</b> <code>{total_supply} шт.</code>"
    keyboard = {"inline_keyboard": [[{"text": "🛒 КУПИТЬ", "url": market_link}]]}
    
    # Получаем список всех админов из базы
    admins_url = f"{SUPABASE_URL}/rest/v1/admins?select=user_id"
    try:
        admins = requests.get(admins_url, headers=SUPABASE_HEADERS, timeout=5).json()
    except:
        admins = []
    
    # Собираем получателей: главный админ + все из базы
    recipients = [MAIN_ADMIN_ID] + [a["user_id"] for a in admins]
    
    # Отправляем всем
    for uid in set(recipients):
        if uid == 0: continue
        url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": uid, "text": text, "parse_mode": "HTML", "reply_markup": keyboard}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Ошибка отправки {uid}: {e}")

def monitor_market():
    print("🟢 Сканер подарков запущен...")
    while True:
        try:
            gifts = fetch_available_gifts()
            for gift in gifts:
                gift_id = str(gift.get("id"))
                if not is_known(gift_id):
                    mark_known(gift_id, gift.get("name", "Unknown"))
                    send_alert_to_admins(gift)
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            time.sleep(10)

# --- Обработка сообщений ---
def handle_message(message):
    chat_id = message["chat"]["id"]
    username = message["from"].get("username", "Аноним")
    text = message.get("text", "").strip().lower()

    # 1. Проверяем, есть ли доступ у пользователя
    has_access = is_admin(chat_id)

    # 2. Обработка команд
    if text == "/start":
        if has_access:
            send_message(chat_id, f"👋 Привет, @{username}!\n🆔 Твой ID: <code>{chat_id}</code>\n\n"
                                  f"✅ У тебя есть доступ к парсеру.\n"
                                  f"📋 **Команды:**\n"
                                  f"/status — проверить работу\n"
                                  f"/admins — список админов")
            if chat_id == MAIN_ADMIN_ID:
                send_message(chat_id, "👑 Ты главный админ.\n/a [ID] — выдать админку\n/d [ID] — забрать админку")
        else:
            send_message(chat_id, f"⛔️ У тебя нет доступа.\nНапиши @inoagent и скинь свой ID: <code>{chat_id}</code>")
        return

    # Если нет доступа — бот игнорирует все остальные команды
    if not has_access:
        send_message(chat_id, "⛔️ У тебя нет доступа. Напиши @inoagent.")
        return

    # --- Команды для админов ---
    if text == "/status":
        try:
            count = len(requests.get(f"{SUPABASE_URL}/rest/v1/known_gifts?select=gift_id", headers=SUPABASE_HEADERS).json())
            send_message(chat_id, f"🟢 Сканер работает.\n📦 В базе: {count} подарков.")
        except:
            send_message(chat_id, "🟢 Сканер работает, но база недоступна.")

    elif text == "/admins":
        try:
            admins = requests.get(f"{SUPABASE_URL}/rest/v1/admins?select=user_id,username", headers=SUPABASE_HEADERS).json()
            msg = f"👑 <b>Главный админ:</b> <code>{MAIN_ADMIN_ID}</code>\n\n"
            if admins:
                msg += "📋 <b>Доп. админы:</b>\n"
                for a in admins:
                    msg += f"• <code>{a['user_id']}</code> (@{a['username']})\n"
            else:
                msg += "📋 Доп. админов нет."
            send_message(chat_id, msg)
        except:
            send_message(chat_id, "Ошибка получения списка.")

    # --- Команды только для главного админа ---
    elif text.startswith("/a "):
        if chat_id != MAIN_ADMIN_ID:
            send_message(chat_id, "⛔️ Только главный админ может выдавать доступ.")
            return
        try:
            new_id = int(text.split()[1])
            add_admin(new_id, "unknown")
            send_message(chat_id, f"✅ Пользователь <code>{new_id}</code> теперь админ.")
            # Уведомляем нового админа
            send_message(new_id, "🎉 Тебе выдали доступ к парсеру! Напиши /start.")
        except:
            send_message(chat_id, "❌ Ошибка. Используй: /a 123456789")

    elif text.startswith("/d "):
        if chat_id != MAIN_ADMIN_ID:
            send_message(chat_id, "⛔️ Только главный админ может забирать доступ.")
            return
        try:
            target_id = int(text.split()[1])
            remove_admin(target_id)
            send_message(chat_id, f"🗑 Админка у <code>{target_id}</code> забрана.")
        except:
            send_message(chat_id, "❌ Ошибка. Используй: /d 123456789")

    else:
        send_message(chat_id, "Не понял команду. Напиши /start.")

def bot_loop():
    print("🤖 Бот запущен...")
    last_update_id = None
    while True:
        updates = get_updates(offset=last_update_id)
        if updates.get("ok") and updates.get("result"):
            for update in updates["result"]:
                last_update_id = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])
        time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=monitor_market, daemon=True).start()
    bot_loop()
