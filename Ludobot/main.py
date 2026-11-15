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

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9266548590:AAHZ7YiM5hnO22pRRcTKhADODkRsECvzdPo" 
ADMIN_ID = 5697184715
DB_PATH = "luck.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- СОСТОЯНИЯ ДЛЯ ИЗМЕНЕНИЯ ТЕКСТОВ ---
class EditText(StatesGroup):
    waiting_for_new_text = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица юзеров (кулдаун)
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, last_play REAL DEFAULT 0)")
        
        # Таблица с текстами
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_texts (
                key TEXT PRIMARY KEY,
                text TEXT
            )
        """)
        
        # Дефолтные тексты, если база пустая
        default_texts = {
            "start": "🎲 <b>Правила игры «Бесконечная лудка»</b> 💡\n\n1️⃣ Отправь <tg-emoji emoji-id=\"5368324207243627318\">🎰</tg-emoji> в чат\n2️⃣ Сообщение автоматически спишет 1 ⭐️\n3️⃣ Если выпадет 7️⃣7️⃣7️⃣ — ты получаешь приз!\n\n🎁 <b>Призы:</b>\n⭐️ Звезды (от 1 до 15)\n💎 Уникальный NFT (Шанс 0.2%!)\n\nУдачи, игрок! ♠️",
            "win_nft_chat": "🤯 <b>НЕВЕРОЯТНО!</b> {user_name} выбил 7️⃣7️⃣7️⃣!\n\n🎁 Выигрыш: <b>УНИКАЛЬНЫЙ NFT!</b>\n👑 Админ свяжется с победителем!",
            "win_nft_admin": "🚨 <b>ВЫИГРАН NFT!</b>\n\nИгрок: <a href='tg://user?id={user_id}'>{user_name}</a> (@{username})\nПриз: <b>Уникальный NFT</b>\nВыдай вручную!",
            "win_stars_chat": "🥳 {user_name} выбил 7️⃣7️⃣7️⃣!\n⭐️ Выигрыш: <b>{stars_won} Telegram Stars!</b>",
            "win_stars_admin": "💰 <b>ВЫИГРАНЫ ЗВЕЗДЫ!</b>\n\nИгрок: <a href='tg://user?id={user_id}'>{user_name}</a> (@{username})\nПриз: <b>{stars_won} ⭐️</b>\nСкинь ему подарок в профиль!",
            "lose": "{user_name}, крутанул: {combo}\n\n❌ Не повезло. Попробуй еще раз!",
            "cooldown": "⏳ Подожди 5 секунд перед следующим спином!"
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
            if row and (now - row[0]) < 5: 
                return False
            await db.execute("INSERT OR REPLACE INTO users (user_id, last_play) VALUES (?, ?)", (user_id, now))
            await db.commit()
            return True

# --- АДМИН ПАНЕЛЬ ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Стартовое сообщение", callback_data="edit_start")],
        [InlineKeyboardButton(text="🏆 Выигрыш NFT (в чат)", callback_data="edit_win_nft_chat")],
        [InlineKeyboardButton(text="🚨 Выигрыш NFT (тебе в ЛС)", callback_data="edit_win_nft_admin")],
        [InlineKeyboardButton(text="⭐️ Выигрыш Звезд (в чат)", callback_data="edit_win_stars_chat")],
        [InlineKeyboardButton(text="💰 Выигрыш Звезд (тебе в ЛС)", callback_data="edit_win_stars_admin")],
        [InlineKeyboardButton(text="❌ Проигрыш", callback_data="edit_lose")],
        [InlineKeyboardButton(text="⏳ Кулдаун", callback_data="edit_cooldown")]
    ])
    await message.answer("🛠 <b>Админ-панель</b>\nВыбери, какой текст хочешь изменить:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_callback(call: CallbackQuery, state: FSMContext):
    key = call.data.replace("edit_", "")
    current_text = await get_text(key)
    
    await state.update_data(edit_key=key)
    await state.set_state(EditText.waiting_for_new_text)
    
    await call.message.edit_text(
        f"📄 <b>Текущий текст:</b>\n\n{current_text}\n\n"
        f"👇 <i>Отправь мне новый текст сообщением (можешь использовать HTML и премиум-эмодзи). Переменные вроде {'{user_name}'} оставляй на месте!</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="cancel_edit")]])
    )
    await call.answer()

@dp.callback_query(F.data == "cancel_edit")
async def cancel_edit(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Редактирование отменено.")
    await call.answer()

@dp.message(EditText.waiting_for_new_text, F.from_user.id == ADMIN_ID)
async def save_new_text(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("edit_key")
    
    # Сохраняем новый текст
    await set_text(key, message.html_text) # html_text сохраняет теги премиум-эмодзи!
    await state.clear()
    
    await message.answer(f"✅ <b>Успешно!</b> Текст для <code>{key}</code> обновлен.\n\nВот как он выглядит:\n\n{message.html_text}")

# --- КОМАНДА СТАРТ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = await get_text("start")
    await message.answer(text)

# --- ОБРАБОТКА СЛОТА 🎰 ---
@dp.message(F.text == "🎰")
async def slot_handler(message: Message):
    if not await check_cooldown(message.from_user.id):
        cd_text = await get_text("cooldown")
        await message.reply(cd_text)
        return

    user_name = message.from_user.first_name
    user_id = message.from_user.id
    username = message.from_user.username or "нет_юзернейма"
    
    chance = random.randint(1, 1000)
    
    # 0.2% шанс на NFT
    if chance <= 2:
        chat_text = await get_text("win_nft_chat")
        admin_text = await get_text("win_nft_admin")
        
        await message.reply(chat_text.format(user_name=user_name))
        
        try:
            await bot.send_message(ADMIN_ID, admin_text.format(user_name=user_name, user_id=user_id, username=username))
        except Exception as e:
            logging.error(f"Ошибка отправки админу: {e}")

    # 15% шанс на Звезды
    elif chance <= 150:
        stars_won = random.choice([1, 2, 5, 10, 15])
        chat_text = await get_text("win_stars_chat")
        admin_text = await get_text("win_stars_admin")
        
        await message.reply(chat_text.format(user_name=user_name, stars_won=stars_won))
        
        try:
            await bot.send_message(ADMIN_ID, admin_text.format(user_name=user_name, user_id=user_id, username=username, stars_won=stars_won))
        except Exception as e:
            logging.error(f"Ошибка отправки админу: {e}")

    # Проигрыш
    else:
        bad_combos = ["🍒 | 🍋 | 🔔", "🍋 | 7️⃣ | BAR", "🍇 | 🍇 | 🍒", "7️⃣ | 🍒 | 🍋"]
        combo = random.choice(bad_combos)
        lose_text = await get_text("lose")
        await message.reply(lose_text.format(user_name=user_name, combo=combo))

# --- ЗАПУСК ---
async def main():
    await init_db()
    print("Бот с админкой запущен! 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
