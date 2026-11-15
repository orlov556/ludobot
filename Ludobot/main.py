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
MAIN_ADMIN_ID = int(os.getenv("5697184715", "5697184715"))
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
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_active', 'on')")
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (MAIN_ADMIN_ID,))
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('spins', 0)")
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('stars_won', 0)")
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('nft_won', 0)")
        
        # Новый красивый текст для старта
        default_texts = {
            "start": (
                "🎲 <b>Бесконечная лудка ✨</b>\n\n"
                "Привет! 🐱 Крути слоты в чате, и если выпадет 7️⃣7️⃣7️⃣ — забирай приз! 🐱\n\n"
                "👇 <b>Выбери действие:</b>"
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
            if row and (now - row[0]) < 3: return False
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
            await db.execute("INSERT INTO player_stats (user_id, username, name, total_stars) VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET total_stars = total_stars + excluded.total_stars, username = excluded.username, name = excluded.name", (user_id, username, name, stars_amount))
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
    except TelegramBadRequest as e:
        logging.error(f"Ошибка HTML: {e}. Отправляю как текст.")
        await message.reply(text, parse_mode=None)

async def safe_send_admin(text: str):
    for admin_id in await get_all_admins():
        try:
            await bot.send_message(admin_id, text)
        except TelegramBadRequest:
            await bot.send_message(admin_id, text, parse_mode=None)
        except Exception as e:
            logging.error(f"Ошибка отправки админу {admin_id}: {e}")

# --- СТАРТ И КНОПКИ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = await get_text("start")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Как играть", callback_data="how_to_play")],
        [InlineKeyboardButton(text="🎲 Перейти в чат", url="https://t.me/LudkaNFTRENT")]
    ])
    
    await message.answer(text, reply_markup=keyboard)

# ОБРАБОТКА КНОПКИ "КАК ИГРАТЬ"
@dp.callback_query(F.data == "how_to_play")
async def how_to_play(call: CallbackQuery):
    rules_text = (
        "🎲 <b>Правила игры «Бесконечная лудка»</b> 💡\n\n"
        "1️⃣ Зайди в групповой чат с ботом\n"
        "2️⃣ Отправь 🎰 (слот-машину)\n"
        "3️⃣ Если выпадет 7️⃣7️⃣7️⃣ (джекпот) — ты получаешь право выбрать ячейку с призом!\n"
        "4️⃣ Нажми на 🎁 и забери выигрыш 🐱\n\n"
        "🎯 Все призы спрятаны случайным образом. Удачи, игрок! ♠️"
    )
    # Отправляем правила новым сообщением
    await call.message.answer(rules_text)
    # Убираем часики с кнопки
    await call.answer()

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
    bot_status = await get_setting("bot_active")
    status_text = "🟢 ВКЛ" if bot_status == "on" else "🔴 ВЫКЛ"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Тексты", callback_data="menu_texts"), InlineKeyboardButton(text="⚙️ Шансы", callback_data="menu_chances")],
        [InlineKeyboardButton(text="👥 Админы", callback_data="manage_admins"), InlineKeyboardButton(text="📊 Статистика", callback_data="stats_menu")],
        [InlineKeyboardButton(text=f"Игра в чате: {status_text}", callback_data="toggle_bot")]
    ])
    await call.message.edit_text("🛠 <b>Главное меню админки</b>\nВыбери раздел:", reply_markup=keyboard)
    await call.answer(f"Игра теперь: {status_text}")

@dp.callback_query(F.data == "stats_menu")
async def stats_menu(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    stats = await get_stats()
    spins, stars_won, nft_won = stats.get('spins', 0), stats.get('stars_won', 0), stats.get('nft_won', 0)
    profit = spins - stars_won
    text = f"📊 <b>Статистика Бота:</b>\n\n🎰 Всего прокрутов: <b>{spins}</b>\n⭐️ Собрано звезд: <b>{spins}</b>\n💸 Выдано звезд: <b>{stars_won}</b>\n💎 Выдано NFT: <b>{nft_won}</b>\n\n📈 <b>Чистый профит (звезды):</b> <b>{profit}</b>"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="main_admin")]]))

@dp.callback_query(F.data == "menu_texts")
async def menu_texts(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Стартовое", callback_data="edit_start")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="edit_win_25"), InlineKeyboardButton(text="⭐️ 50", callback_data="edit_win_50")],
        [InlineKeyboardButton(text="⭐️ 100", callback_data="edit_win_100"), InlineKeyboardButton(text="💎 NFT", callback_data="edit_win_nft_chat")],
        [InlineKeyboardButton(text="🚨 Админу", callback_data="edit_admin_win")],
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
    await call.message.edit_text(f"📄 <b>Текущий текст:</b>\n\n<code>{current_text}</code>\n\n👇 <i>Отправь новый текст:</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="main_admin")]]))
    await call.answer()

@dp.message(EditText.waiting_for_new_text)
async def save_new_text(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    data = await state.get_data()
    await set_text(data.get("edit_key"), message.html_text)
    await state.clear()
    await message.answer("✅ Текст обновлен!")

@dp.callback_query(F.data == "menu_chances")
async def menu_chances(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    chances = await get_chances()
    text = f"⚙️ <b>Шансы (на 777):</b>\n\n💎 NFT: <b>{chances.get('nft', 0)}%</b>\n🤯 100⭐: <b>{chances.get('100', 0)}%</b>\n🔥 50⭐: <b>{chances.get('50', 0)}%</b>\n🥳 25⭐: <b>Остаток (Гарант)</b>"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 NFT", callback_data="chance_nft"), InlineKeyboardButton(text="🤯 100⭐", callback_data="chance_100")],
        [InlineKeyboardButton(text="🔥 50⭐", callback_data="chance_50")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_admin")]
    ])
    await call.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("chance_"))
async def edit_chance_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    await state.update_data(chance_prize=call.data.replace("chance_", ""))
    await state.set_state(ChangeChance.waiting_for_value)
    await call.message.edit_text("Введи новый шанс в процентах (можно дробные).\nЧтобы отменить, нажми /cancel")

@dp.message(ChangeChance.waiting_for_value)
async def save_chance(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админку", callback_data="main_admin")]]))
        return
    try:
        val = float(message.text.replace(",", "."))
        if not (0 <= val <= 100): raise ValueError
        data = await state.get_data()
        await set_chance(data.get("chance_prize"), val)
        await state.clear()
        await message.answer(f"✅ Шанс изменен на <b>{val}%</b>!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админку", callback_data="main_admin")]]))
    except ValueError:
        await message.answer("❌ Нужно число от 0 до 100.")

@dp.callback_query(F.data == "manage_admins")
async def manage_admins_menu(call: CallbackQuery):
    if not await is_admin(call.from_user.id): return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin")], [InlineKeyboardButton(text="🔙 Назад", callback_data="main_admin")]])
    await call.message.edit_text("👥 <b>Управление админами</b>:", reply_markup=keyboard)

@dp.callback_query(F.data == "add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    await state.set_state(AdminManage.waiting_for_new_admin_id)
    await call.message.edit_text("Отправь <b>числовой ID</b> нового админа.\n\n/cancel для отмены")

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
        await message.answer("❌ Это не ID.")

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

# --- КОМАНДА /top ---
@dp.message(Command("top"))
async def top_players(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name, username, total_stars FROM player_stats ORDER BY total_stars DESC LIMIT 10") as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await message.reply("🏆 Пока нет игроков с выигрышами. Стань первым!")
        return
    top_text = "🏆 <b>Топ-10 игроков:</b>\n\n"
    for i, (name, username, stars) in enumerate(rows, 1):
        if not stars or stars == 0: continue
        user_link = f"@{username}" if username else name
        top_text += f"{i}. {user_link} — <b>{stars} ⭐️</b>\n"
    await message.reply(top_text)

# --- ИГРА (ОБРАБОТКА АНИМИРОВАННОГО СЛОТА) ---
@dp.message(F.dice)
async def slot_handler_dice(message: Message):
    if message.dice.emoji != "🎰":
        return
    await process_slot(message)

async def process_slot(message: Message):
    if await get_setting("bot_active") == "off":
        return
    if not await check_cooldown(message.from_user.id):
        return

    user_name, user_id, username = message.from_user.first_name, message.from_user.id, message.from_user.username or ""
    chances = await get_chances()
    roll = random.uniform(0, 100)
    
    current_chance = 0
    prize_type, stars_won = '25', 25
    
    current_chance += chances.get('nft', 0)
    if roll <= current_chance:
        prize_type, stars_won = 'nft', 0
    else:
        current_chance += chances.get('100', 0)
        if roll <= current_chance:
            prize_type, stars_won = '100', 100
        else:
            current_chance += chances.get('50', 0)
            if roll <= current_chance:
                prize_type, stars_won = '50', 50

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
