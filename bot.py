import os
import sqlite3
import threading
import time
from flask import Flask
import requests
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    ReplyKeyboardMarkup,
)

BOT_TOKEN = "9133972042:AAFfGkCcTzPsvhifOZWOSDncVrBAJzRmf9U"
ADMIN_ID = 8200259525  # Sizning ID raqamingiz

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

# --- RENDER WEB SERVICE UCHUN FLASK SERVER ---
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running 24/7!"


def run_flask():
    # Render avtomatik beradigan PORT o'zgaruvchisini oladi (default: 10000)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect("moliya.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL
        )
    """)

    conn.commit()

    # Standart qiymatlar
    defaults = {
        "stars_amount": "10",
        "usd_rate": "12800",
        "rub_rate": "140",
        "ton_rate": "55000",
    }
    for key, val in defaults.items():
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)", (key, val)
            )
            conn.commit()

    conn.close()


def get_balance(user_id: int) -> float:
    conn = sqlite3.connect("moliya.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,)
        )
        conn.commit()
        balance = 0.0
    else:
        balance = row[0]
    conn.close()
    return balance


def update_balance(user_id: int, amount: float, tx_type: str):
    current = get_balance(user_id)
    new_balance = current + amount
    conn = sqlite3.connect("moliya.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id)
    )
    cursor.execute(
        "INSERT INTO history (user_id, type, amount) VALUES (?, ?, ?)",
        (user_id, tx_type, amount),
    )
    conn.commit()
    conn.close()
    return new_balance


def get_setting(key: str, default: str) -> str:
    conn = sqlite3.connect("moliya.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = sqlite3.connect("moliya.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE settings SET value = ? WHERE key = ?", (value, key)
    )
    conn.commit()
    conn.close()


init_db()


# --- AVTOMATIK VALYUTA YANGILASH (HAR 10 MINUTDA) ---
def update_exchange_rates_background():
    while True:
        try:
            res = requests.get(
                "https://cbu.uz/uz/arkhiv-kursov-valyut/json/", timeout=10
            )
            if res.status_code == 200:
                data = res.json()
                for item in data:
                    if item["Ccy"] == "USD":
                        set_setting("usd_rate", str(float(item["Rate"])))
                    elif item["Ccy"] == "RUB":
                        set_setting("rub_rate", str(float(item["Rate"])))

            res_ton = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=uzs",
                timeout=10,
            )
            if res_ton.status_code == 200:
                ton_uzs = (
                    res_ton.json()
                    .get("the-open-network", {})
                    .get("uzs")
                )
                if ton_uzs:
                    set_setting("ton_rate", str(float(ton_uzs)))
        except Exception as e:
            print(f"Valyuta yangilashda xatolik: {e}")

        time.sleep(600)


threading.Thread(
    target=update_exchange_rates_background, daemon=True
).start()


# --- TUGMALAR ---
def get_main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("➕ Pul qo'shish"), KeyboardButton("➖ Xarajat"))
    kb.add(KeyboardButton("💰 Balans"), KeyboardButton("💱 Valyuta kursi"))
    kb.add(KeyboardButton("⭐ Stars (Pont)"), KeyboardButton("📊 Tarix"))
    return kb


def get_admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("💱 Dollar kursini o'zgartirish"))
    kb.add(KeyboardButton("💱 Rubl kursini o'zgartirish"))
    kb.add(KeyboardButton("🪙 TON kursini o'zgartirish"))
    kb.add(KeyboardButton("⭐ Stars narxini o'zgartirish"))
    kb.add(KeyboardButton("🔙 Asosiy menyu"))
    return kb


@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_states.pop(message.from_user.id, None)
    bal = get_balance(message.from_user.id)
    usd_rate = float(get_setting("usd_rate", "12800"))
    usd_bal = bal / usd_rate if usd_rate > 0 else 0

    bot.send_message(
        message.chat.id,
        f"Salom! Shaxsiy moliya botingiz tayyor.\n\n"
        f"💳 Balansingiz: *{bal:,.0f} so'm* (~${usd_bal:.2f})",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown",
    )


# --- ADMIN PANEL ---
@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if message.from_user.id == ADMIN_ID:
        user_states.pop(message.from_user.id, None)
        bot.send_message(
            message.chat.id,
            "👑 Admin panelga xush kelibsiz!",
            reply_markup=get_admin_keyboard(),
        )
    else:
        bot.send_message(message.chat.id, "❌ Siz admin emassiz!")


@bot.message_handler(func=lambda message: message.text == "🔙 Asosiy menyu")
def back_to_main(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        "Asosiy menyuga qaytdingiz:",
        reply_markup=get_main_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == "💰 Balans")
def show_balance(message):
    user_states.pop(message.from_user.id, None)
    bal = get_balance(message.from_user.id)
    usd_rate = float(get_setting("usd_rate", "12800"))
    rub_rate = float(get_setting("rub_rate", "140"))
    ton_rate = float(get_setting("ton_rate", "55000"))

    usd_bal = bal / usd_rate if usd_rate > 0 else 0
    rub_bal = bal / rub_rate if rub_rate > 0 else 0
    ton_bal = bal / ton_rate if ton_rate > 0 else 0

    bot.send_message(
        message.chat.id,
        f"💳 Joriy balansingiz: *{bal:,.0f} so'm*\n\n"
        f"💵 Dollarda: *${usd_bal:.2f}*\n"
        f"🇷🇺 Rublda: *₽{rub_bal:.2f}*\n"
        f"💎 TONda: *~{ton_bal:.4f} TON*",
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda message: message.text == "💱 Valyuta kursi")
def show_currency_rate(message):
    user_states.pop(message.from_user.id, None)
    usd = float(get_setting("usd_rate", "12800"))
    rub = float(get_setting("rub_rate", "140"))
    ton = float(get_setting("ton_rate", "55000"))

    bot.send_message(
        message.chat.id,
        f"💱 *Hozirgi mashhur valyuta kurslari:*\n"
        f"(Har 10 minutda avtomatik yangilanib turadi)\n\n"
        f"🇺🇸 1 USD = *{usd:,.2f} so'm*\n"
        f"🇷🇺 1 RUB = *{rub:,.2f} so'm*\n"
        f"💎 1 TON = *{ton:,.2f} so'm*",
        parse_mode="Markdown",
    )


# --- TARIX ---
@bot.message_handler(func=lambda message: message.text == "📊 Tarix")
def show_history(message):
    user_states.pop(message.from_user.id, None)
    conn = sqlite3.connect("moliya.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, amount FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5",
        (message.from_user.id,),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(
            message.chat.id, "📭 Hozircha operatsiyalar tarixi bo'sh."
        )
        return

    text = "📜 *Oxirgi 5 ta operatsiyangiz:*\n\n"
    for r in rows:
        t_type, amt = r
        if t_type == "income":
            text += f"➕ Qo'shildi: +{amt:,.0f} so'm\n"
        else:
            text += f"➖ Xarajat: -{abs(amt):,.0f} so'm\n"

    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda message: message.text == "➕ Pul qo'shish")
def add_income_start(message):
    user_states[message.from_user.id] = "waiting_for_income"
    bot.send_message(
        message.chat.id,
        "Qancha pul qo'shmoqchisiz? (Faqat raqam yozing, masalan: 50000)",
    )


@bot.message_handler(func=lambda message: message.text == "➖ Xarajat")
def add_expense_start(message):
    user_states[message.from_user.id] = "waiting_for_expense"
    bot.send_message(
        message.chat.id,
        "Qancha xarajat qildingiz? (Faqat raqam yozing, masalan: 15000)",
    )


# --- ADMIN BOSHQARUVI ---
@bot.message_handler(
    func=lambda message: message.text == "💱 Dollar kursini o'zgartirish"
)
def admin_change_usd(message):
    if message.from_user.id == ADMIN_ID:
        user_states[message.from_user.id] = "waiting_for_new_usd_rate"
        bot.send_message(
            message.chat.id,
            f"Hozirgi USD: {get_setting('usd_rate', '12800')}\nYangi narxni yuboring:",
        )
    else:
        bot.send_message(message.chat.id, "❌ Ruxsat yo'q!")


@bot.message_handler(
    func=lambda message: message.text == "💱 Rubl kursini o'zgartirish"
)
def admin_change_rub(message):
    if message.from_user.id == ADMIN_ID:
        user_states[message.from_user.id] = "waiting_for_new_rub_rate"
        bot.send_message(
            message.chat.id,
            f"Hozirgi RUB: {get_setting('rub_rate', '140')}\nYangi narxni yuboring:",
        )
    else:
        bot.send_message(message.chat.id, "❌ Ruxsat yo'q!")


@bot.message_handler(
    func=lambda message: message.text == "🪙 TON kursini o'zgartirish"
)
def admin_change_ton(message):
    if message.from_user.id == ADMIN_ID:
        user_states[message.from_user.id] = "waiting_for_new_ton_rate"
        bot.send_message(
            message.chat.id,
            f"Hozirgi TON: {get_setting('ton_rate', '55000')}\nYangi narxni yuboring:",
        )
    else:
        bot.send_message(message.chat.id, "❌ Ruxsat yo'q!")


@bot.message_handler(
    func=lambda message: message.text == "⭐ Stars narxini o'zgartirish"
)
def admin_change_stars(message):
    if message.from_user.id == ADMIN_ID:
        user_states[message.from_user.id] = "waiting_for_new_stars_price"
        bot.send_message(
            message.chat.id,
            f"Hozirgi Stars: {get_setting('stars_amount', '10')}\nYangi narxni yuboring:",
        )
    else:
        bot.send_message(message.chat.id, "❌ Ruxsat yo'q!")


# --- TELEGRAM STARS ---
@bot.message_handler(func=lambda message: message.text == "⭐ Stars (Pont)")
def send_stars_invoice(message):
    user_states.pop(message.from_user.id, None)
    price_val = int(get_setting("stars_amount", "10"))
    prices = [LabeledPrice(label="VIP Pont", amount=price_val)]

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            text=f"⭐ {price_val} Stars tashlash", pay=True
        )
    )

    bot.send_invoice(
        chat_id=message.chat.id,
        title="VIP Status (Pont)",
        description=f"Bot balansiga {price_val} Telegram Stars o'tkazish.",
        invoice_payload="pont_stars_payload",
        provider_token="",
        currency="XTR",
        prices=prices,
        reply_markup=kb,
    )


@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout_handler(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@bot.message_handler(content_types=["successful_payment"])
def successful_payment_handler(message):
    stars_amount = message.successful_payment.total_amount
    bot.send_message(
        message.chat.id,
        f"🔥 Rahmat! Bot hisobiga *{stars_amount} Stars* tushdi!",
        parse_mode="Markdown",
    )


# --- MATNLAR VA HOLATLAR ---
@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
)
def process_state_input(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    text = message.text

    if text in [
        "➕ Pul qo'shish",
        "➖ Xarajat",
        "💰 Balans",
        "💱 Valyuta kursi",
        "⭐ Stars (Pont)",
        "📊 Tarix",
        "🔙 Asosiy menyu",
    ]:
        user_states.pop(user_id, None)
        bot.process_new_messages([message])
        return

    if state == "waiting_for_income":
        if not text.isdigit():
            bot.send_message(
                message.chat.id, "Iltimos, faqat musbat raqam kiriting:"
            )
            return
        amount = float(text)
        new_bal = update_balance(user_id, amount, "income")
        user_states.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            f"✅ *+{amount:,.0f} so'm* qo'shildi!\n"
            f"💰 Yangi balans: *{new_bal:,.0f} so'm*",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown",
        )

    elif state == "waiting_for_expense":
        if not text.isdigit():
            bot.send_message(
                message.chat.id, "Iltimos, faqat musbat raqam kiriting:"
            )
            return
        amount = float(text)
        new_bal = update_balance(user_id, -amount, "expense")
        user_states.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            f"🔻 *-{amount:,.0f} so'm* ayrildi!\n"
            f"💰 Qolgan balans: *{new_bal:,.0f} so'm*",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown",
        )

    elif state == "waiting_for_new_usd_rate":
        set_setting("usd_rate", text)
        user_states.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            f"✅ USD kursi *{text} so'm* qilib o'zgartirildi!",
            reply_markup=get_admin_keyboard(),
        )

    elif state == "waiting_for_new_rub_rate":
        set_setting("rub_rate", text)
        user_states.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            f"✅ RUB kursi *{text} so'm* qilib o'zgartirildi!",
            reply_markup=get_admin_keyboard(),
        )

    elif state == "waiting_for_new_ton_rate":
        set_setting("ton_rate", text)
        user_states.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            f"✅ TON kursi *{text} so'm* qilib o'zgartirildi!",
            reply_markup=get_admin_keyboard(),
        )

    elif state == "waiting_for_new_stars_price":
        set_setting("stars_amount", text)
        user_states.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            f"✅ Stars narxi *{text} Stars* qilib o'zgartirildi!",
            reply_markup=get_admin_keyboard(),
        )


if __name__ == "__main__":
    # Flask serverini alohida oqimda (thread) ishga tushiramiz (Web Service talabini qondirish uchun)
    threading.Thread(target=run_flask, daemon=True).start()

    # Botni ishga tushirish
    print("Bot ishga tushdi...")
    bot.infinity_polling()
