import time
import requests
import threading
import os
from flask import Flask

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "1780244500:ynwsVbg3UOT8ceBWXxShNAk9j9nqTr_E6ti"
NYX_API_BASE = "https://nyxgram.new.tg"

# Данные из Supabase (перепроверь URL!)
SUPABASE_URL = "https://xktkhtxdmjjbqllsbpkp.supabase.co" 
SUPABASE_KEY = "sb_publishable_6R6LPZooWoTfoyEm9BErgQ_8NnHCYzg"

MAIN_ADMIN_ID = 1780243908
CHECK_INTERVAL = 2.0
# ============================================

# Flask для Render
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Работа с Supabase (через requests) ---
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

# --- Логика бота ---
def get_updates(offset=None):
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        resp = requests.get(url, params=params, timeout=40)
        return resp.json()
    except Exception as e:
        print(f"Ошибка getUpdates: {e}")
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
    except Exception as e:
        print(f"Ошибка сети: {e}")
        return []

def send_alert(gift):
    gift_id = str(gift.get("id", "unknown"))
    name = gift.get("name", "Без названия")
    price = gift.get("price", "?")
    total_supply = gift.get("total_supply", "?")
    market_link = f"https://t.me/gift/{gift_id}" 
    
    text = f"⚡️ <b>НОВЫЙ ДРОП!</b> ⚡️\n\n🎁 <b>Подарок:</b> <a href='{market_link}'>{name}</a>\n💸 <b>Цена:</b> <code>{price} ⭐</code>\n📦 <b>Тираж:</b> <code>{total_supply} шт.</code>"
    
    url = f"{NYX_API_BASE}/bot{BOT_TOKEN}/sendMessage"
    keyboard = {"inline_keyboard": [[{"text": "🛒 КУПИТЬ", "url": market_link}]]}
    payload = {"chat_id": MAIN_ADMIN_ID, "text": text, "parse_mode": "HTML", "reply_markup": keyboard}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def monitor_market():
    print("🟢 Сканер запущен...")
    while True:
        try:
            gifts = fetch_available_gifts()
            for gift in gifts:
                gift_id = str(gift.get("id"))
                if not is_known(gift_id):
                    mark_known(gift_id, gift.get("name", "Unknown"))
                    send_alert(gift)
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            time.sleep(10)

def bot_loop():
    print("🤖 Бот запущен (HTTP polling)...")
    last_update_id = None
    while True:
        updates = get_updates(offset=last_update_id)
        if updates.get("ok") and updates.get("result"):
            for update in updates["result"]:
                last_update_id = update["update_id"] + 1
                if "message" in update:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")
                    if text == "/start":
                        send_message(chat_id, f"👋 Привет!\n🆔 Твой ID: <code>{chat_id}</code>")
        time.sleep(1)

if __name__ == "__main__":
    # Запускаем Flask в потоке
    threading.Thread(target=run_flask, daemon=True).start()
    # Запускаем сканер и бота в главном потоке
    threading.Thread(target=monitor_market, daemon=True).start()
    bot_loop()
