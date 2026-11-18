import sqlite3
import threading
import time
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
    defaults = {"stars_amount": "10", "usd_rate": "12800", "rub_rate": "140", "ton_rate": "55000"}
    for key, val in defaults.items():
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, val))
            conn.commit()

    conn.close()


def get_balance(user_id: int) -> float:
    conn = sqlite3.connect("moliya.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
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
    cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    cursor.execute("INSERT INTO history (user_id, type, amount) VALUES (?, ?, ?)", (user_id, tx_type, amount))
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
    cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()


init_db()


# --- AVTOMATIK VALYUTA YANGILASH (HAR 10 MINUTDA) ---
def update_exchange_rates_background():
    while True:
        try:
            # 1. USD va RUB uchun Markaziy Bank API
            res = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/", timeout=10)
            if res.status_code == 200:
                data = res.json()
                for item in data:
                    if item["Ccy"] == "USD":
                        set_setting("usd_rate", str(float(item["Rate"])))
                    elif item["Ccy"] == "RUB":
                        set_setting("rub_rate", str(float(item["Rate"])))

            # 2. TON uchun CoinGecko API (so'mdagi narxi)
            res_ton = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=uzs", timeout=10)
            if res_ton.status_code == 200:
                ton_uzs = res_ton.json().get("the-open-network", {}).get("uzs")
                if ton_uzs:
                    set_setting("ton_rate", str(float(ton_uzs)))
        except Exception as e:
            print(f"Valyuta yangilashda xatolik: {e}")

        # 10 minut kutish (10 * 60 sekund)
        time.sleep(600)


# Fon rejimida ishga tushiramiz
threading.Thread(target=update_exchange_rates_background, daemon=True).start()


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
    
