
import asyncio
import random
import logging
import aiosqlite
import time
import os
import html
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest


# =====================================================
# НАСТРОЙКИ
# =====================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_ЕСЛИ_НЕ_В_ПЕРЕМЕННЫХ")
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", "5697184715"))

DB_PATH = os.getenv("DB_PATH", "/data/luck.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()


# =====================================================
# СОСТОЯНИЯ
# =====================================================

class EditText(StatesGroup):
    waiting_for_new_text = State()


class AdminManage(StatesGroup):
    waiting_for_new_admin_id = State()


class ChangeChance(StatesGroup):
    waiting_for_value = State()


# =====================================================
# ТЕКСТЫ ПО УМОЛЧАНИЮ
# =====================================================

DEFAULT_TEXTS = {
    "start": (
        "🎲 <b>Бесконечная лудка ✨</b>\n\n"
        "Привет! 🐱 Крути слоты в чате, и если выпадет "
        "7️⃣7️⃣7️⃣ — забирай приз! 🐱\n\n"
        "👇 <b>Выбери действие:</b>"
    ),

    "welcome": (
        "👋 <b>Добро пожаловать, {user_name}!</b>\n\n"
        "🎲 Ты попал в Бесконечную лудку!\n"
        "🍀 Желаем удачи и больших выигрышей!"
    ),

    "rules": (
        "🎲 <b>Правила игры «Бесконечная лудка»</b> 💡\n\n"
        "1️⃣ Зайди в групповой чат с ботом.\n"
        "2️⃣ Отправь 🎰 (слот-машину).\n"
        "3️⃣ Если выпадет 7️⃣7️⃣7️⃣ — ты получаешь право "
        "выбрать ячейку с призом!\n"
        "4️⃣ Нажми на 🎁 и забери выигрыш 🐱\n\n"
        "🎯 Все призы спрятаны случайным образом. Удачи, игрок! ♠️"
    ),

    "win_25": (
        "🥳 {user_name} выбил 7️⃣7️⃣7️⃣!\n"
        "⭐️ Выигрыш: <b>25 Telegram Stars!</b>"
    ),

    "win_50": (
        "🔥 {user_name} выбил 7️⃣7️⃣7️⃣!\n"
        "⭐️ Выигрыш: <b>50 Telegram Stars!</b>"
    ),

    "win_100": (
        "🤯 {user_name} выбил 7️⃣7️⃣7️⃣!\n"
        "⭐️ Выигрыш: <b>100 Telegram Stars!</b>"
    ),

    "win_nft_chat": (
        "💎 <b>ДЖЕКПОТ!</b> {user_name} выбил 7️⃣7️⃣7️⃣!\n"
        "🎁 Выигрыш: <b>УНИКАЛЬНЫЙ NFT!</b>"
    ),

    "admin_win": (
        "🚨 <b>ВЫИГРЫШ!</b>\n\n"
        "Игрок: <a href='tg://user?id={user_id}'>{user_name}</a> "
        "(@{username})\n"
        "Приз: <b>{prize}</b>\n\n"
        "Выдай вручную!"
    )
}


# =====================================================
# СОСТОЯНИЕ БАЗЫ ДАННЫХ
# =====================================================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                last_play REAL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_texts (
                key TEXT PRIMARY KEY,
                text TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chances (
                prize TEXT PRIMARY KEY,
                chance REAL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS player_stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT,
                total_stars INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('bot_active', 'on')
        """)

        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
            (MAIN_ADMIN_ID,)
        )

        await db.execute("""
            INSERT OR IGNORE INTO stats (key, value)
            VALUES ('spins', 0)
        """)

        await db.execute("""
            INSERT OR IGNORE INTO stats (key, value)
            VALUES ('stars_won', 0)
        """)

        await db.execute("""
            INSERT OR IGNORE INTO stats (key, value)
            VALUES ('nft_won', 0)
        """)

        # Добавляем все стандартные тексты.
        # INSERT OR IGNORE не перезаписывает тексты,
        # которые ты уже сохранил через админку.

        for key, text in DEFAULT_TEXTS.items():
            await db.execute(
                """
                INSERT OR IGNORE INTO bot_texts (key, text)
                VALUES (?, ?)
                """,
                (key, text)
            )

        default_chances = {
            "nft": 0.01,
            "100": 1.0,
            "50": 5.0
        }

        for key, value in default_chances.items():
            await db.execute(
                """
                INSERT OR IGNORE INTO chances (prize, chance)
                VALUES (?, ?)
                """,
                (key, value)
            )

        await db.commit()

    logging.info("База данных успешно загружена.")


# =====================================================
# ХЕЛПЕРЫ БАЗЫ ДАННЫХ
# =====================================================

async def get_text(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT text FROM bot_texts WHERE key = ?",
            (key,)
        ) as cursor:
            row = await cursor.fetchone()

    return row[0] if row else "Текст не найден."


async def set_text(key: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO bot_texts (key, text)
            VALUES (?, ?)
            """,
            (key, text)
        )
        await db.commit()


async def get_chances() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT prize, chance FROM chances"
        ) as cursor:
            rows = await cursor.fetchall()

    return {row[0]: row[1] for row in rows}


async def set_chance(prize: str, chance: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE chances SET chance = ? WHERE prize = ?",
            (chance, prize)
        )
        await db.commit()


async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,)
        ) as cursor:
            row = await cursor.fetchone()

    return row[0] if row else ""


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE settings SET value = ? WHERE key = ?",
            (value, key)
        )
        await db.commit()


async def check_cooldown(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_play FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        now = time.time()

        if row and (now - row[0]) < 3:
            return False

        await db.execute(
            """
            INSERT OR REPLACE INTO users (user_id, last_play)
            VALUES (?, ?)
            """,
            (user_id, now)
        )

        await db.commit()
        return True


async def is_admin(user_id: int) -> bool:
    if user_id == MAIN_ADMIN_ID:
        return True

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM admins WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def get_all_admins() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM admins"
        ) as cursor:
            rows = await cursor.fetchall()

    return [row[0] for row in rows]


# =====================================================
# ФОРМАТИРОВАНИЕ ТЕКСТОВ
# =====================================================

class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def format_text(template: str, **kwargs) -> str:
    safe_values = {
        key: html.escape(str(value))
        for key, value in kwargs.items()
    }

    try:
        return template.format_map(SafeDict(safe_values))
    except (ValueError, KeyError):
        return template


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


# =====================================================
# БЕЗОПАСНАЯ ОТПРАВКА
# =====================================================

async def safe_reply(message: Message, text: str):
    try:
        await message.reply(text)
    except TelegramBadRequest as error:
        logging.error("Ошибка HTML при отправке: %s", error)

        await message.reply(
            strip_html(text),
            parse_mode=None
        )


async def safe_answer(message: Message, text: str, **kwargs):
    try:
        await message.answer(text, **kwargs)
    except TelegramBadRequest as error:
        logging.error("Ошибка HTML при отправке: %s", error)

        await message.answer(
            strip_html(text),
            parse_mode=None,
            **kwargs
        )


async def safe_send_admin(text: str):
    for admin_id in await get_all_admins():
        try:
            await bot.send_message(admin_id, text)

        except TelegramBadRequest as error:
            logging.error(
                "Ошибка HTML для админа %s: %s",
                admin_id,
                error
            )

            try:
                await bot.send_message(
                    admin_id,
                    strip_html(text),
                    parse_mode=None
                )
            except Exception as second_error:
                logging.error(
                    "Не удалось отправить сообщение админу %s: %s",
                    admin_id,
                    second_error
                )

        except Exception as error:
            logging.error(
                "Ошибка отправки админу %s: %s",
                admin_id,
                error
            )


# =====================================================
# КЛАВИАТУРЫ АДМИНКИ
# =====================================================

def main_admin_keyboard(status: str):
    status_text = "🟢 ВКЛ" if status == "on" else "🔴 ВЫКЛ"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📝 Тексты",
                callback_data="menu_texts"
            ),
            InlineKeyboardButton(
                text="⚙️ Шансы",
                callback_data="menu_chances"
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 Админы",
                callback_data="manage_admins"
            ),
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="stats_menu"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Игра в чате: {status_text}",
                callback_data="toggle_bot"
            )
        ]
    ])


def texts_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📝 Стартовое сообщение",
                callback_data="edit_start"
            )
        ],
        [
            InlineKeyboardButton(
                text="👋 Приветствие участников",
                callback_data="edit_welcome"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎰 Правила игры",
                callback_data="edit_rules"
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐️ 25 Stars",
                callback_data="edit_win_25"
            ),
            InlineKeyboardButton(
                text="⭐️ 50 Stars",
                callback_data="edit_win_50"
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐️ 100 Stars",
                callback_data="edit_win_100"
            ),
            InlineKeyboardButton(
                text="💎 NFT",
                callback_data="edit_win_nft_chat"
            )
        ],
        [
            InlineKeyboardButton(
                text="🚨 Сообщение админу",
                callback_data="edit_admin_win"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="main_admin"
            )
        ]
    ])


# =====================================================
# КОМАНДА START
# =====================================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = await get_text("start")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎰 Как играть",
                callback_data="how_to_play"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎲 Перейти в чат",
                url="https://t.me/LudkaNFTRENT"
            )
        ]
    ])

    await safe_answer(
        message,
        text,
        reply_markup=keyboard
    )


# =====================================================
# ПРИВЕТСТВИЕ НОВЫХ УЧАСТНИКОВ
# =====================================================

@dp.message(F.new_chat_members)
async def welcome_new_members(message: Message):
    welcome_text = await get_text("welcome")

    for member in message.new_chat_members:

        if member.is_bot:
            continue

        user_name = member.first_name or "Игрок"

        text = format_text(
            welcome_text,
            user_name=user_name
        )

        await safe_answer(message, text)

        logging.info(
            "Новый участник: %s (%s)",
            member.first_name,
            member.id
        )


# =====================================================
# КНОПКА КАК ИГРАТЬ
# =====================================================

@dp.callback_query(F.data == "how_to_play")
async def how_to_play(call: CallbackQuery):
    rules_text = await get_text("rules")

    await safe_answer(call.message, rules_text)
    await call.answer()


# =====================================================
# АДМИН ПАНЕЛЬ
# =====================================================

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        return

    status = await get_setting("bot_active")

    await message.answer(
        "🛠 <b>Главное меню админки</b>\n"
        "Выбери раздел:",
        reply_markup=main_admin_keyboard(status)
    )


# =====================================================
# ВКЛЮЧЕНИЕ / ВЫКЛЮЧЕНИЕ ИГРЫ
# =====================================================

@dp.callback_query(F.data == "toggle_bot")
async def toggle_bot(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("Нет доступа!", show_alert=True)
        return

    current = await get_setting("bot_active")
    new_status = "off" if current == "on" else "on"

    await set_setting("bot_active", new_status)

    await call.message.edit_text(
        "🛠 <b>Главное меню админки</b>\n"
        "Выбери раздел:",
        reply_markup=main_admin_keyboard(new_status)
    )

    status_text = "🟢 ВКЛ" if new_status == "on" else "🔴 ВЫКЛ"

    await call.answer(f"Игра теперь: {status_text}")


# =====================================================
# СТАТИСТИКА
# =====================================================

@dp.callback_query(F.data == "stats_menu")
async def stats_menu(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return

    stats = await get_stats()

    spins = stats.get("spins", 0)
    stars_won = stats.get("stars_won", 0)
    nft_won = stats.get("nft_won", 0)

    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"🎰 Всего джекпотов: <b>{spins}</b>\n"
        f"⭐️ Выиграно Stars: <b>{stars_won}</b>\n"
        f"💎 Выдано NFT: <b>{nft_won}</b>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="main_admin"
            )
        ]
    ])

    await call.message.edit_text(
        text,
        reply_markup=keyboard
    )

    await call.answer()


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT key, value FROM stats"
        ) as cursor:
            rows = await cursor.fetchall()

    return {row[0]: row[1] for row in rows}


# =====================================================
# МЕНЮ РЕДАКТИРОВАНИЯ ТЕКСТОВ
# =====================================================

@dp.callback_query(F.data == "menu_texts")
async def menu_texts(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return

    await call.message.edit_text(
        "📝 <b>Редактирование текстов</b>\n\n"
        "Выбери сообщение, которое хочешь изменить.\n"
        "Premium Emoji поддерживаются!",
        reply_markup=texts_keyboard()
    )

    await call.answer()


# =====================================================
# РЕДАКТИРОВАНИЕ ТЕКСТОВ
# =====================================================

@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_callback(
    call: CallbackQuery,
    state: FSMContext
):
    if not await is_admin(call.from_user.id):
        return

    key = call.data.replace("edit_", "", 1)

    allowed_keys = set(DEFAULT_TEXTS.keys())

    if key not in allowed_keys:
        await call.answer("Неизвестный текст.", show_alert=True)
        return

    await state.update_data(edit_key=key)
    await state.set_state(EditText.waiting_for_new_text)

    current_text = await get_text(key)

    await call.message.edit_text(
        "📄 <b>Текущий текст:</b>\n\n"
        f"{current_text}\n\n"
        "👇 <b>Отправь новый текст следующим сообщением.</b>\n\n"
        "Можно использовать обычные эмодзи, Premium Emoji "
        "и HTML-форматирование.\n\n"
        "Для отмены нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="menu_texts"
                )
            ]
        ])
    )

    await call.answer()


# =====================================================
# СОХРАНЕНИЕ НОВОГО ТЕКСТА
# =====================================================

@dp.message(EditText.waiting_for_new_text)
async def save_new_text(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    key = data.get("edit_key")

    if key not in DEFAULT_TEXTS:
        await state.clear()
        await message.answer("❌ Ошибка. Выбери текст заново.")
        return

    # html_text сохраняет HTML-представление entities,
    # в том числе Premium Emoji с tg-emoji emoji-id.

    new_text = message.html_text

    if not new_text:
        await message.answer(
            "❌ Отправь именно текстовое сообщение, "
            "а не фотографию или стикер."
        )
        return

    await set_text(key, new_text)
    await state.clear()

    await message.answer(
        "✅ <b>Текст успешно обновлён!</b>\n\n"
        "Premium Emoji и форматирование сохранены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 К текстам",
                    callback_data="menu_texts"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛠 В админку",
                    callback_data="main_admin"
                )
            ]
        ])
    )


# =====================================================
# ШАНСЫ
# =====================================================

@dp.callback_query(F.data == "menu_chances")
async def menu_chances(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return

    chances = await get_chances()

    text = (
        "⚙️ <b>Шансы на джекпоте 777:</b>\n\n"
        f"💎 NFT: <b>{chances.get('nft', 0)}%</b>\n"
        f"🤯 100 Stars: <b>{chances.get('100', 0)}%</b>\n"
        f"🔥 50 Stars: <b>{chances.get('50', 0)}%</b>\n"
        "🥳 25 Stars: <b>Остаток (гарант)</b>\n\n"
        "Сумма трёх изменяемых шансов не должна превышать 100%."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💎 NFT",
                callback_data="chance_nft"
            ),
            InlineKeyboardButton(
                text="🤯 100 Stars",
                callback_data="chance_100"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔥 50 Stars",
                callback_data="chance_50"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="main_admin"
            )
        ]
    ])

    await call.message.edit_text(
        text,
        reply_markup=keyboard
    )

    await call.answer()


@dp.callback_query(F.data.startswith("chance_"))
async def edit_chance_start(
    call: CallbackQuery,
    state: FSMContext
):
    if not await is_admin(call.from_user.id):
        return

    prize = call.data.replace("chance_", "", 1)

    if prize not in ("nft", "100", "50"):
        await call.answer("Неизвестный приз.", show_alert=True)
        return

    await state.update_data(chance_prize=prize)
    await state.set_state(ChangeChance.waiting_for_value)

    await call.message.edit_text(
        "⚙️ <b>Изменение шанса</b>\n\n"
        "Введи новый шанс в процентах.\n"
        "Можно использовать дробные числа.\n\n"
        "Например: <code>0.5</code>\n\n"
        "Для отмены нажми /cancel"
    )

    await call.answer()


@dp.message(ChangeChance.waiting_for_value)
async def save_chance(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    if not message.text:
        await message.answer("❌ Отправь число.")
        return

    if message.text.strip() == "/cancel":
        await state.clear()
        await message.answer(
            "Отменено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 В админку",
                        callback_data="main_admin"
                    )
                ]
            ])
        )
        return

    try:
        value = float(message.text.replace(",", "."))

        if not (0 <= value <= 100):
            raise ValueError

        data = await state.get_data()
        prize = data.get("chance_prize")

        chances = await get_chances()

        total = (
            value
            + sum(
                chances.get(key, 0)
                for key in ("nft", "100", "50")
                if key != prize
            )
        )

        if total > 100:
            await message.answer(
                f"❌ Сумма шансов будет {total:.4f}%.\n"
                "Она не может превышать 100%."
            )
            return

        await set_chance(prize, value)
        await state.clear()

        await message.answer(
            f"✅ Шанс изменён на <b>{value}%</b>!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚙️ К шансам",
                        callback_data="menu_chances"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🛠 В админку",
                        callback_data="main_admin"
                    )
                ]
            ])
        )

    except ValueError:
        await message.answer(
            "❌ Нужно ввести число от 0 до 100."
        )


# =====================================================
# УПРАВЛЕНИЕ АДМИНАМИ
# =====================================================

@dp.callback_query(F.data == "manage_admins")
async def manage_admins_menu(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="➕ Добавить админа",
                callback_data="add_admin"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="main_admin"
            )
        ]
    ])

    await call.message.edit_text(
        "👥 <b>Управление админами</b>:",
        reply_markup=keyboard
    )

    await call.answer()


@dp.callback_query(F.data == "add_admin")
async def add_admin_start(
    call: CallbackQuery,
    state: FSMContext
):
    if not await is_admin(call.from_user.id):
        return

    await state.set_state(AdminManage.waiting_for_new_admin_id)

    await call.message.edit_text(
        "Отправь <b>числовой ID</b> нового админа.\n\n"
        "/cancel для отмены"
    )

    await call.answer()


@dp.message(AdminManage.waiting_for_new_admin_id)
async def add_admin_save(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    if not message.text:
        await message.answer("❌ Отправь числовой ID.")
        return

    if message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return

    try:
        new_admin_id = int(message.text.strip())

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
                (new_admin_id,)
            )
            await db.commit()

        await state.clear()

        await message.answer(
            f"✅ ID <code>{new_admin_id}</code> добавлен!"
        )

    except ValueError:
        await message.answer("❌ Это не числовой ID.")


# =====================================================
# ВОЗВРАТ В ГЛАВНОЕ МЕНЮ
# =====================================================

@dp.callback_query(F.data == "main_admin")
async def back_to_main_admin(
    call: CallbackQuery,
    state: FSMContext
):
    await state.clear()

    if not await is_admin(call.from_user.id):
        return

    status = await get_setting("bot_active")

    await call.message.edit_text(
        "🛠 <b>Главное меню админки</b>\n"
        "Выбери раздел:",
        reply_markup=main_admin_keyboard(status)
    )

    await call.answer()


# =====================================================
# ОТМЕНА ДЕЙСТВИЙ
# =====================================================

@dp.message(Command("cancel"))
async def cancel_action(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if not current_state:
        return

    await state.clear()

    await message.answer(
        "❌ Действие отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛠 В админку",
                    callback_data="main_admin"
                )
            ]
        ])
    )


# =====================================================
# ТОП ИГРОКОВ
# =====================================================

@dp.message(Command("top"))
async def top_players(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT name, username, total_stars
            FROM player_stats
            ORDER BY total_stars DESC
            LIMIT 10
            """
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.reply(
            "🏆 Пока нет игроков с выигрышами. Стань первым!"
        )
        return

    top_text = "🏆 <b>Топ-10 игроков:</b>\n\n"

    position = 0

    for name, username, stars in rows:
        if not stars or stars <= 0:
            continue

        position += 1

        if username:
            user_link = "@" + html.escape(username)
        else:
            user_link = html.escape(name or "Игрок")

        top_text += (
            f"{position}. {user_link} — "
            f"<b>{stars} ⭐️</b>\n"
        )

    await safe_reply(message, top_text)


# =====================================================
# СТАТИСТИКА ИГРОКОВ
# =====================================================

async def update_stats(
    user_id: int,
    name: str,
    username: str,
    prize_type: str,
    stars_amount: int
):
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            "UPDATE stats SET value = value + 1 WHERE key = 'spins'"
        )

        await db.execute(
            """
            UPDATE stats
            SET value = value + ?
            WHERE key = 'stars_won'
            """,
            (stars_amount,)
        )

        if prize_type == "nft":
            await db.execute(
                """
                UPDATE stats
                SET value = value + 1
                WHERE key = 'nft_won'
                """
            )

        await db.execute(
            """
            INSERT INTO player_stats
                (user_id, username, name, total_stars)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                total_stars = total_stars + excluded.total_stars,
                username = excluded.username,
                name = excluded.name
            """,
            (user_id, username, name, stars_amount)
        )

        await db.commit()


# =====================================================
# ОБРАБОТКА СЛОТА
# =====================================================

@dp.message(F.dice)
async def slot_handler_dice(message: Message):

    # Игнорируем все другие игровые кубики.
    if message.dice.emoji != "🎰":
        return

    # 64 — результат 777 в Telegram Slot Machine.
    # Только за этот результат выдаём приз.
    if message.dice.value != 64:
        return

    await process_slot(message)


async def process_slot(message: Message):

    if await get_setting("bot_active") == "off":
        return

    if not message.from_user:
        return

    if not await check_cooldown(message.from_user.id):
        return

    user_name = message.from_user.first_name or "Игрок"
    user_id = message.from_user.id
    username = message.from_user.username or ""

    chances = await get_chances()

    roll = random.uniform(0, 100)

    current_chance = 0

    prize_type = "25"
    stars_won = 25

    current_chance += chances.get("nft", 0)

    if roll < current_chance:
        prize_type = "nft"
        stars_won = 0

    else:
        current_chance += chances.get("100", 0)

        if roll < current_chance:
            prize_type = "100"
            stars_won = 100

        else:
            current_chance += chances.get("50", 0)

            if roll < current_chance:
                prize_type = "50"
                stars_won = 50

    await update_stats(
        user_id,
        user_name,
        username,
        prize_type,
        stars_won
    )

    # Подготавливаем данные игрока.
    user_data = {
        "user_name": user_name,
        "user_id": user_id,
        "username": username or "нет"
    }

    admin_template = await get_text("admin_win")

    if prize_type == "nft":

        win_text = format_text(
            await get_text("win_nft_chat"),
            **user_data
        )

        admin_text = format_text(
            admin_template,
            **user_data,
            prize="УНИКАЛЬНЫЙ NFT 💎"
        )

    elif prize_type == "100":

        win_text = format_text(
            await get_text("win_100"),
            **user_data
        )

        admin_text = format_text(
            admin_template,
            **user_data,
            prize="100 ⭐️"
        )

    elif prize_type == "50":

        win_text = format_text(
            await get_text("win_50"),
            **user_data
        )

        admin_text = format_text(
            admin_template,
            **user_data,
            prize="50 ⭐️"
        )

    else:

        win_text = format_text(
            await get_text("win_25"),
            **user_data
        )

        admin_text = format_text(
            admin_template,
            **user_data,
            prize="25 ⭐️"
        )

    await safe_reply(message, win_text)

    await safe_send_admin(admin_text)


# =====================================================
# ЗАПУСК БОТА
# =====================================================

async def main():
    await init_db()

    logging.info("Бесконечная лудка запущена!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
