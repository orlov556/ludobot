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
BOT_TOKEN = os.getenv("9266548590:AAHZ7YiM5hnO22pRRcTKhADODkRsECvzdPo", "9266548590:AAHZ7YiM5hnO22pRRcTKhADODkRsECvzdPo") 
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", "5697184715"))
DB_PATH = "/data/luck.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- СОСТОЯНИЯ ---
class EditText(StatesGroup):
    waiting_for_new_text = State()

class AdminManage(StatesGroup):
    waiting_for_new_admin_id = State()

class ChangeChance(StatesGroup):
    waiting_for_value = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, last_play REAL DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS bot_texts (key TEXT PRIMARY KEY, text TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS chances (prize TEXT PRIMARY KEY, chance REAL)")
        await db.execute("CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS player_stats (user_id INTEGER PRIMARY KEY, username TEXT, name TEXT, total_stars INTEGER DEFAULT 0)")
        
        # Таблица для настроек (Вкл/Выкл бота в чате)
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_active', 'on')")
        
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (MAIN_ADMIN_ID,))
        
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('spins', 0)")
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('stars_won', 0)")
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('nft_won', 0)")
        
        default_texts = {
            "start": (
                "🎲 <b>Правила игры «Бесконечная лудка»</b> 💡\n\n"
                "1️⃣ Отправь 🎰 в чат\n"
                "2️⃣ Сообщение автоматически спишет 1 ⭐️\n"
                "3️⃣ Если выпадет 7️⃣7️⃣7️⃣ — ты получаешь приз!\n\n"
                "🎁 <b>Шансы на выигрыш при 777:</b>\n"
                "⭐️ <b>25 Звезд</b> — Высокий шанс (Гарант)\n"
                "⭐️ <b>50 Звезд</b> — Средний шанс\n"
                "⭐️ <b>100 Звезд</b> — Низкий шанс\n"
                "💎 <b>Уникальный NFT</b> — Джекпот (0.01%)\n\n"
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
            
        default_chances = {"nft": 0.01, "100": 1.0, "50": 5.0}
        for key, val in default_chances.items():
            await db.execute("INSERT OR IGNORE INTO chances (prize, chance) VALUES (?, ?)", (key, val))
            
        await db.commit()

# --- ХЕЛПЕРЫ БД ---
async def get_text(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT text FROM bot_texts WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "Текст не найден."

async def set_text(key: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bot_texts SET text = ? WHERE key = ?", (text, key))
        await db.commit()

async def get_chances() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT prize, chance FROM chances") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

async def set_chance(prize: str, chance: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE chances SET chance = ? WHERE prize = ?", (chance, prize))
        await db.commit()

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
        await db.commit()

async def check_cooldown(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_play FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            now = time.time()
            if row and (now - row[0]) < 3: 
                return False
            await db.execute("INSERT OR REPLACE INTO users (user_id, last_play) VALUES (?, ?)", (user_id, now))
            await db.commit()
            return True

async def is_admin(user_id: int) -> bool:
    if user_id == MAIN_ADMIN_ID: return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def get_all_admins() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# --- СТАТИСТИКА ---
async def update_stats(user_id: int, name: str, username: str, prize_type: str, stars_amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE stats SET value = value + 1 WHERE key = 'spins'")
        await db.execute("UPDATE stats SET value = value + ? WHERE key = 'stars_won'", (stars_amount,))
        if prize_type == 'nft':
            await db.execute("UPDATE stats SET value = value + 1 WHERE key = 'nft_won'")
        
        if stars_amount > 0 or prize_type == 'nft':
            await db.execute("""
                INSERT INTO player_stats (user_id, username, name, total_stars) 
                VALUES (?, ?, ?, ?) 
                ON CONFLICT(user_id) DO UPDATE SET 
                    total_stars = total_stars + excluded.total_stars,
                    username = excluded.username,
                    name = excluded.name
            """, (user_id, username, name, stars_amount))
        await db.commit()

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, value FROM stats") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

# --- БЕЗОПАСНАЯ ОТПРАВКА ---
async def safe_reply(message: Message, text: str):
    try:
        await message.reply(text)
    except TelegramBadRequest:
        await message.reply(text, parse_mode=None)

async def safe_send_admin(text: str):
    admins = await get_all_admins()
    for admin_id in admins:
        try:
            await bot.send_message(admin_id, text)
        except TelegramBadRequest:
            await bot.send_message(admin_id, text, parse_mode=None)
        except Exception as e:
            logging.error(f"Ошибка отправки админу {admin_id}: {e}")

# --- АДМИН ПАНЕЛЬ ---
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id): return
        
    bot_status = await get_setting("bot_active")
    status_text = "🟢 ВКЛ" if bot_status == "on" else "🔴 ВЫКЛ"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Тексты", callback_data="menu_texts"), InlineKeyboardButton(text="⚙️ Шансы", callback_data="menu_chances")],
        [InlineKeyboardButton(text="👥 Админы", callback_data="manage_admins"), InlineKeyboardButton(text="📊 Статистика", callback_data="stats_menu")],
        [InlineKeyboardButton(text=f"Игра в чате: {status_text}", callback_data="toggle_bot")]
    ])
    await message.answer("🛠 <b>Главное меню админки</b>\nВыбери раздел:", reply_markup=keyboard)

@dp.callback_query(F.data == "toggle_bot")
async def toggle_bot(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    current = await get_setting("bot_active")
    new_status = "off" if current == "on" else "on"
    await set_setting("bot_active", new_status)
    
    # Обновляем кнопку
    bot_status = await get_setting("bot_active")
    status_text = "🟢 ВКЛ" if bot_status == "on" else "🔴 ВЫКЛ"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Тексты", callback_data="menu_texts"), InlineKeyboardButton(text="⚙️ Шансы", callback_data="menu_chances")],
        [InlineKeyboardButton(text="👥 Админы", callback_data="manage_admins"), InlineKeyboardButton(text="📊 Статистика", callback_data="stats_menu")],
        [InlineKeyboardButton(text=f"Игра в чате: {status_text}", callback_data="toggle_bot")]
    ])
    await call.message.edit_text("🛠 <b>Главное меню админки</b>\nВыбери раздел:", reply_markup=keyboard)
    await call.answer(f"Игра теперь: {status_text}")

# --- СТАТИСТИКА В АДМИНКЕ ---
@dp.callback_query(F.data == "stats_menu")
async def stats_menu(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    stats = await get_stats()
    spins = stats.get('spins', 0)
    stars_won = stats.get('stars_won', 0)
    nft_won = stats.get('nft_won', 0)
    
    stars_spent = spins 
    profit = stars_spent - stars_won
    
    text = (
        f"📊 <b>Статистика Бота:</b>\n\n"
        f"🎰 Всего прокрутов: <b>{spins}</b>\n"
        f"⭐️ Собрано звезд: <b>{stars_spent}</b>\n"
        f"💸 Выдано звезд: <b>{stars_won}</b>\n"
        f"💎 Выдано NFT: <b>{nft_won}</b>\n\n"
        f"📈 <b>Чистый профит (звезды):</b> <b>{profit}</b>"
    )
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="main_admin")]]))

# --- УПРАВЛЕНИЕ ТЕКСТАМИ ---
@dp.callback_query(F.data == "menu_texts")
async def menu_texts(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Стартовое", callback_data="edit_start")],
        [InlineKeyboardButton(text="⭐️ Выигрыш 25", callback_data="edit_win_25"), InlineKeyboardButton(text="⭐️ Выигрыш 50", callback_data="edit_win_50")],
        [InlineKeyboardButton(text="⭐️ Выигрыш 100", callback_data="edit_win_100"), InlineKeyboardButton(text="💎 Выигрыш NFT", callback_data="edit_win_nft_chat")],
        [InlineKeyboardButton(text="🚨 Уведомление Админу", callback_data="edit_admin_win")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_admin")]
    ])
    await call.message.edit_text("📝 <b>Редактирование текстов</b>:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_callback(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    key = call.data.replace("edit_", "")
    current_text = await get_text(key)
    
    await state.update_data(edit_key=key)
    await state.set_state(EditText.waiting_for_new_text)
    
    await call.message.edit_text(f"📄 <b>Текущий текст:</b>\n\n{current_text}\n\n👇 <i>Отправь новый текст:</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="main_admin")]])
    )
    await call.answer()

@dp.message(EditText.waiting_for_new_text)
async def save_new_text(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    data = await state.get_data()
    key = data.get("edit_key")
    await set_text(key, message.html_text)
    await state.clear()
    await message.answer(f"✅ Текст обновлен!")

# --- УПРАВЛЕНИЕ ШАНСАМИ ---
@dp.callback_query(F.data == "menu_chances")
async def menu_chances(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    chances = await get_chances()
    
    text = (
        f"⚙️ <b>Текущие шансы (на 777):</b>\n\n"
        f"💎 NFT: <b>{chances.get('nft', 0)}%</b>\n"
        f"🤯 100⭐: <b>{chances.get('100', 0)}%</b>\n"
        f"🔥 50⭐: <b>{chances.get('50', 0)}%</b>\n"
        f"🥳 25⭐: <b>Остаток (Гарант)</b>\n\n"
        f"<i>Выбери, какой шанс изменить:</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 NFT", callback_data="chance_nft"), InlineKeyboardButton(text="🤯 100⭐", callback_data="chance_100")],
        [InlineKeyboardButton(text="🔥 50⭐", callback_data="chance_50")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_admin")]
    ])
    await call.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("chance_"))
async def edit_chance_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    prize = call.data.replace("chance_", "")
    
    await state.update_data(chance_prize=prize)
    await state.set_state(ChangeChance.waiting_for_value)
    
    await call.message.edit_text(f"Введи новый шанс для приза <b>{prize}</b> в процентах.\n<i>Можно писать дробные числа.</i>\n\nЧтобы отменить, нажми /cancel")

@dp.message(ChangeChance.waiting_for_value)
async def save_chance(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админку", callback_data="main_admin")]]))
        return
    try:
        val = float(message.text.replace(",", "."))
        if val < 0 or val > 100:
            await message.answer("❌ Шанс должен быть от 0 до 100.")
            return
        data = await state.get_data()
        prize = data.get("chance_prize")
        await set_chance(prize, val)
        await state.clear()
        await message.answer(f"✅ Шанс для <b>{prize}</b> изменен на <b>{val}%</b>!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админку", callback_data="main_admin")]]))
    except ValueError:
        await message.answer("❌ Это не число.")

# --- УПРАВЛЕНИЕ АДМИНАМИ ---
@dp.callback_query(F.data == "manage_admins")
async def manage_admins_menu(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_admin")]
    ])
    await call.message.edit_text("👥 <b>Управление админами</b>:", reply_markup=keyboard)

@dp.callback_query(F.data == "add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    await state.set_state(AdminManage.waiting_for_new_admin_id)
    await call.message.edit_text("Отправь мне <b>числовой ID</b> нового админа.\n\nЧтобы отменить, напиши /cancel")

@dp.message(AdminManage.waiting_for_new_admin_id)
async def add_admin_save(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админку", callback_data="main_admin")]]))
        return
    try:
        new_admin_id = int(message.text.strip())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
            await db.commit()
        await state.clear()
        await message.answer(f"✅ ID <code>{new_admin_id}</code> добавлен!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админку", callback_data="main_admin")]]))
    except ValueError:
        await message.answer("❌ Это не ID. Отправь только цифры.")

@dp.callback_query(F.data == "main_admin")
async def back_to_main_admin(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not await is_admin(call.from_user.id): return
    bot_status = await get_setting("bot_active")
    status_text = "🟢 ВКЛ" if bot_status == "on" else "🔴 ВЫКЛ"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Тексты", callback_data="menu_texts"), InlineKeyboardButton(text="⚙️ Шансы", callback_data="menu_chances")],
        [InlineKeyboardButton(text="👥 Админы", callback_data="manage_admins"), InlineKeyboardButton(text="📊 Статистика", callback_data="stats_menu")],
        [InlineKeyboardButton(text=f"Игра в чате: {status_text}", callback_data="toggle_bot")]
    ])
    await call.message.edit_text("🛠 <b>Главное меню админки</b>\nВыбери раздел:", reply_markup=keyboard)

# --- КОМАНДА СТАРТ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = await get_text("start")
    await safe_reply(message, text)

# --- ТОП ИГРОКОВ ---
@dp.message(Command("top"))
async def top_players(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name, username, total_stars FROM player_stats ORDER BY total_stars DESC LIMIT 10") as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        await message.reply("🏆 Пока нет игроков с выигрышами. Стань первым!")
        return
        
    top_text = "🏆 <b>Топ-10 игроков по выигранным звездам:</b>\n\n"
    for i, row in enumerate(rows, 1):
        name, username, stars = row
        if not stars or stars == 0: continue
        user_link = f"@{username}" if username else name
        top_text += f"{i}. {user_link} — <b>{stars} ⭐️</b>\n"
        
    await message.reply(top_text)

# --- ОБРАБОТКА СЛОТА 🎰 ---
@dp.message(F.text == "🎰")
async def slot_handler(message: Message):
    # Проверяем, включен ли бот (если выключен — молчим)
    bot_status = await get_setting("bot_active")
    if bot_status == "off":
        return

    if not await check_cooldown(message.from_user.id):
        return

    user_name = message.from_user.first_name
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    chances = await get_chances()
    roll = random.uniform(0, 100)
    
    current_chance = 0
    prize_type = '25'
    stars_won = 25
    
    # Проверяем НФТ
    current_chance += chances.get('nft', 0)
    if roll <= current_chance:
        prize_type = 'nft'
        stars_won = 0
    else:
        current_chance += chances.get('100', 0)
        if roll <= current_chance:
            prize_type = '100'
            stars_won = 100
        else:
            current_chance += chances.get('50', 0)
            if roll <= current_chance:
                prize_type = '50'
                stars_won = 50
            else:
                prize_type = '25'
                stars_won = 25

    await update_stats(user_id, user_name, username, prize_type, stars_won)

    if prize_type == 'nft':
        await safe_reply(message, (await get_text("win_nft_chat")).format(user_name=user_name))
        await safe_send_admin((await get_text("admin_win")).format(user_name=user_name, user_id=user_id, username=username or "нет", prize="УНИКАЛЬНЫЙ NFT 💎"))
    elif prize_type == '100':
        await safe_reply(message, (await get_text("win_100")).format(user_name=user_name))
        await safe_send_admin((await get_text("admin_win")).format(user_name=user_name, user_id=user_id, username=username or "нет", prize="100 ⭐️"))
    elif prize_type == '50':
        await safe_reply(message, (await get_text("win_50")).format(user_name=user_name))
        await safe_send_admin((await get_text("admin_win")).format(user_name=user_name, user_id=user_id, username=username or "нет", prize="50 ⭐️"))
    else:
        await safe_reply(message, (await get_text("win_25")).format(user_name=user_name))
        await safe_send_admin((await get_text("admin_win")).format(user_name=user_name, user_id=user_id, username=username or "нет", prize="25 ⭐️"))

# --- ЗАПУСК ---
async def main():
    await init_db()
    print("Бот запущен! 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
