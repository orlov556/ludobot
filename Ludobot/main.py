import asyncio
import random
import logging
import aiosqlite
import time
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("9266548590:AAHZ7YiM5hnO22pRRcTKhADODkRsECvzdPo", "ТВОЙ_ТОКЕН_ЕСЛИ_НЕ_В_ПЕРЕМЕННЫХ") 
# Сюда впиши ID всех админов через запятую без пробелов
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "5697184715").split(",") if x]
DB_PATH = "/data/luck.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class EditText(StatesGroup):
    waiting_for_new_text = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, last_play REAL DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS bot_texts (key TEXT PRIMARY KEY, text TEXT)")
        
        # ФАЛЬШИВЫЕ ШАНСЫ ДЛЯ КРАСОТЫ В СТАРТОВОМ СООБЩЕНИИ
        default_texts = {
            "start": (
                "🎲 <b>Правила игры «Бесконечная лудка»</b> 💡\n\n"
                "1️⃣ Отправь 🎰 в чат\n"
                "2️⃣ Сообщение автоматически спишет 1 ⭐️\n"
                "3️⃣ Если выпадет 7️⃣7️⃣7️⃣ — ты получаешь приз!\n\n"
                "🎁 <b>Шансы на выигрыш при 777:</b>\n"
                "⭐️ <b>25 Звезд</b> — Высокий шанс (40%)\n"
                "⭐️ <b>50 Звезд</b> — Средний шанс (20%)\n"
                "⭐️ <b>100 Звезд</b> — Низкий шанс (10%)\n"
                "💎 <b>Уникальный NFT</b> — Джекпот (1%)\n\n"
                "Удачи, игрок! ♠️"
            ),
            "win_25": "🥳 {user_name} выбил 7️⃣7️⃣7️⃣!\n⭐️ Выигрыш: <b>25 Telegram Stars!</b>",
            "win_50": "🔥 {user_name} выбил 7️⃣7️⃣7️⃣!\n⭐️ Выигрыш: <b>50 Telegram Stars!</b>",
            "win_100": "🤯 {user_name} выбил 7️⃣7️⃣7️⃣!\n⭐️ Выигрыш: <b>100 Telegram Stars!</b>",
            "win_nft_chat": "💎 <b>ДЖЕКПОТ!</b> {user_name} выбил 7️⃣7️⃣7️⃣!\n🎁 Выигрыш: <b>УНИКАЛЬНЫЙ NFT!</b>",
            "admin_win": "🚨 <b>ВЫИГРЫШ!</b>\n\nИгрок: <a href='tg://user?id={user_id}'>{user_name}</a> (@{username})\nПриз: <b>{prize}</b>\nВыдай вручную!"
        }
        
        for key, text in default_texts.items():
            await db.execute("INSERT OR IGNORE INTO bot_texts (key, text) VALUES (?, ?)", (key, text))
        await db.commit()

async def get_text(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT text FROM bot_texts WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "Текст не найден."

async def set_text(key: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bot_texts SET text = ? WHERE key = ?", (text, key))
        await db.commit()

async def check_cooldown(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_play FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            now = time.time()
            # Кулдаун 3 секунды
            if row and (now - row[0]) < 3: 
                return False
            await db.execute("INSERT OR REPLACE INTO users (user_id, last_play) VALUES (?, ?)", (user_id, now))
            await db.commit()
            return True

# --- БЕЗОПАСНАЯ ОТПРАВКА ---
async def safe_reply(message: Message, text: str):
    try:
        await message.reply(text)
    except TelegramBadRequest:
        await message.reply(text, parse_mode=None)

async def safe_send_admin(text: str):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except TelegramBadRequest:
            await bot.send_message(admin_id, text, parse_mode=None)
        except Exception as e:
            logging.error(f"Ошибка отправки админу {admin_id}: {e}")

# --- АДМИН ПАНЕЛЬ ---
@dp.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Стартовое сообщение", callback_data="edit_start")],
        [InlineKeyboardButton(text="⭐️ Выигрыш 25", callback_data="edit_win_25")],
        [InlineKeyboardButton(text="⭐️ Выигрыш 50", callback_data="edit_win_50")],
        [InlineKeyboardButton(text="⭐️ Выигрыш 100", callback_data="edit_win_100")],
        [InlineKeyboardButton(text="💎 Выигрыш NFT (чат)", callback_data="edit_win_nft_chat")],
        [InlineKeyboardButton(text="🚨 Уведомление Админу", callback_data="edit_admin_win")]
    ])
    await message.answer("🛠 <b>Админ-панель</b>\nВыбери текст:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    key = call.data.replace("edit_", "")
    current_text = await get_text(key)
    
    await state.update_data(edit_key=key)
    await state.set_state(EditText.waiting_for_new_text)
    
    await call.message.edit_text(
        f"📄 <b>Текущий текст:</b>\n\n{current_text}\n\n👇 <i>Отправь новый текст.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="cancel_edit")]])
    )
    await call.answer()

@dp.callback_query(F.data == "cancel_edit")
async def cancel_edit(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.")

@dp.message(EditText.waiting_for_new_text, F.from_user.id.in_(ADMIN_IDS))
async def save_new_text(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("edit_key")
    await set_text(key, message.html_text)
    await state.clear()
    await message.answer(f"✅ Текст обновлен!")

# --- КОМАНДА СТАРТ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = await get_text("start")
    await safe_reply(message, text)

# --- ОБРАБОТКА СЛОТА 🎰 ---
@dp.message(F.text == "🎰")
async def slot_handler(message: Message):
    if not await check_cooldown(message.from_user.id):
        return

    user_name = message.from_user.first_name
    user_id = message.from_user.id
    username = message.from_user.username or "нет_юзернейма"
    
    # Рандом от 1 до 10000
    chance = random.randint(1, 10000)
    
    # РЕАЛЬНЫЕ ШАНСЫ (ВСЕГДА ЕСТЬ ПРИЗ):
    # НФТ - 0.01% (1 из 10000)
    # 100 звезд - 0.49% (49 из 10000)
    # 50 звезд - 4.5% (450 из 10000)
    # 25 звезд - 95% (9500 из 10000) - Основная масса
    
    if chance == 1:
        # НФТ
        chat_text = await get_text("win_nft_chat")
        admin_text = await get_text("admin_win")
        await safe_reply(message, chat_text.format(user_name=user_name))
        await safe_send_admin(admin_text.format(user_name=user_name, user_id=user_id, username=username, prize="УНИКАЛЬНЫЙ NFT 💎"))
        
    elif chance <= 50:
        # 100 ЗВЕЗД
        chat_text = await get_text("win_100")
        admin_text = await get_text("admin_win")
        await safe_reply(message, chat_text.format(user_name=user_name))
        await safe_send_admin(admin_text.format(user_name=user_name, user_id=user_id, username=username, prize="100 ⭐️"))
        
    elif chance <= 500:
        # 50 ЗВЕЗД
        chat_text = await get_text("win_50")
        admin_text = await get_text("admin_win")
        await safe_reply(message, chat_text.format(user_name=user_name))
        await safe_send_admin(admin_text.format(user_name=user_name, user_id=user_id, username=username, prize="50 ⭐️"))
        
    else:
        # 25 ЗВЕЗД (В остальных случаях)
        chat_text = await get_text("win_25")
        admin_text = await get_text("admin_win")
        await safe_reply(message, chat_text.format(user_name=user_name))
        await safe_send_admin(admin_text.format(user_name=user_name, user_id=user_id, username=username, prize="25 ⭐️"))

# --- ЗАПУСК ---
async def main():
    await init_db()
    print("Бот запущен! 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
