"""
MAX_BOT — Главный интерфейс max-приложения.
Разработчик: Участник №1
Файл: max_bot.py
"""

import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Импортируем модули сокомандников
import database as db
import auth
import parser as guap_parser

# НАСТРОЙКА ЛОГИРОВАНИЯ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота (замени на свой актуальный токен от BotFather)
BOT_TOKEN = 'YOUR_MAX_BOT_TOKEN'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

def normalize_deadline(raw_deadline: str) -> str:
    """
    Конвертирует дату из ЛК ГУАП (например, '20.07.2026' или '20.07.2026 15:30')
    в формат 'YYYY-MM-DD HH:MM:SS', который требуется для БД напарника.
    """
    if not raw_deadline or not raw_deadline.strip():
        return "2026-12-31 23:59:00"  # Дефолтная заглушка
    
    cleaned = raw_deadline.strip()
    try:
        if len(cleaned) > 10:
            dt = datetime.strptime(cleaned, "%d.%m.%Y %H:%M")
        else:
            dt = datetime.strptime(cleaned, "%d.%m.%Y")
            dt = dt.replace(hour=23, minute=59, second=0)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return cleaned


# ================= КЛАВИАТУРЫ =================

def get_main_menu() -> ReplyKeyboardMarkup:
    """Создает основное меню с кнопками."""
    kb = [
        [KeyboardButton(text="📚 Мои задания"), KeyboardButton(text="⏰ Ближайшие дедлайны")],
        [KeyboardButton(text="🔄 Синхронизировать ЛК")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# ================= ОБРАБОТЧИКИ КОМАНД =================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """/start — Регистрация пользователя по Инструкции (Пункт 1)."""
    max_id = str(message.from_user.id)
    
    # Инициализируем базу данных (создаем таблицы)
    db.init_db()
    
    # Проверяем, есть ли пользователь в БД
    user = db.get_user(max_id)
    if user is None:
        # Если нет — добавляем
        db.add_user(max_id)
        welcome_text = (
            f"Привет, {message.from_user.first_name}! 👋\n"
            f"Я — твой ассистент MAX для ЛК ГУАП.\n\n"
            f"⚠️ *С чего начать?*\n"
            f"Перейди в **👤 Мой профиль** и привяжи свой логин/пароль."
        )
    else:
        welcome_text = f"С возвращением, {message.from_user.first_name}!"

    await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(Command("set_password"))
async def cmd_set_password(message: types.Message):
    """Быстрое обновление пароля (Пункт 5 инструкции)."""
    max_id = str(message.from_user.id)
    
    try:
        new_password = message.text.split(maxsplit=1)[1].strip()
    except IndexError:
        await message.answer("❌ Формат: `/set_password твой_новый_пароль`", parse_mode="Markdown")
        return

    # Вызываем функцию напарника для обновления пароля
    if db.update_user_password(max_id, new_password):
        await message.answer("✅ Пароль успешно изменен!")
    else:
        await message.answer("❌ Ошибка при обновлении пароля. Нажми /start.")


# ================= ОБРАБОТКА КНОПОК =================

@dp.message(F.text == "👤 Мой профиль")
async def show_profile(message: types.Message):
    """Просмотр привязанных данных."""
    max_id = str(message.from_user.id)
    user = db.get_user(max_id)
    
    if not user:
        await message.answer("Пожалуйста, напиши сначала /start")
        return

    login_status = f"`{user['login']}`" if user['login'] else "❌ не указан"
    pass_status = "✅ Сохранен" if user['password'] else "❌ не указан"

    profile_text = (
        f"👤 *Профиль MAX:*\n\n"
        f"• *Telegram ID:* `{user['user_id']}`\n"
        f"• *Логин ГУАП:* {login_status}\n"
        f"• *Пароль:* {pass_status}\n\n"
        f"📖 *Как привязать кабинет?*\n"
        f"Отправь боту сообщение в формате: `логин:пароль`"
    )
    
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Удалить аккаунт 🗑", callback_data="delete_account")]
    ])
    
    await message.answer(profile_text, reply_markup=inline_kb, parse_mode="Markdown")


@dp.message(F.text == "📚 Мои задания")
async def show_assignments(message: types.Message):
    """Выводит задания (Исправление критической ошибки Пункта 2)."""
    max_id = str(message.from_user.id)
    user = db.get_user(max_id)
    
    if not user:
        await message.answer("Сначала отправь /start")
        return

    # ИСПРАВЛЕНИЕ: Передаем внутренний id (число), а не строковый Telegram-id
    assignments = db.get_assignments(user['id'])
    
    if not assignments:
        await message.answer("📝 Твой список пуст. Нажми **🔄 Синхронизировать ЛК**.")
        return

    text = "📋 *Твои задания из ГУАП:*\n\n"
    for i, ass in enumerate(assignments, 1):
        status_emoji = "✅" if ass['status'] == "принят" else "⏳"
        text += (
            f"{i}. {status_emoji} *{ass['discipline_name']}*\n"
            f"    🔹 {ass['title']}\n"
            f"    📅 Срок: {ass['deadline']}\n\n"
        )
    
    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "⏰ Ближайшие дедлайны")
async def show_deadlines(message: types.Message):
    """Ближайшие дедлайны на 3 дня (Исправление Пункта 3)."""
    max_id = str(message.from_user.id)
    user = db.get_user(max_id)
    
    if not user:
        await message.answer("Сначала отправь /start")
        return

    # ИСПРАВЛЕНИЕ: Передаем внутренний id (число)
    soon = db.get_assignments_soon(user['id'], 3)
    
    if not soon:
        await message.answer("🎉 Дедлайнов на ближайшие 3 дня нет!")
        return

    text = "⚠️ *Дедлайны на ближайшие 3 дня:*\n\n"
    for ass in soon:
        text += f"🚨 *{ass['discipline_name']}*\n📌 {ass['title']}\n🕒 Дедлайн: {ass['deadline']}\n\n"
        
    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "❓ Помощь")
async def show_help(message: types.Message):
    help_text = (
        "❓ *Справка по командам MAX:*\n\n"
        "• Отправь сообщение `логин:пароль` для привязки аккаунта.\n"
        "• Кнопка `🔄 Синхронизировать ЛК` скачает задания с pro.guap.ru.\n"
        "• Команда `/set_password <пароль>` быстро сменит пароль."
    )
    await message.answer(help_text, parse_mode="Markdown")


# ================= СИНХРОНИЗАЦИЯ С ЛК ГУАП =================

@dp.message(F.text == "🔄 Синхронизировать ЛК")
async def sync_guap_data(message: types.Message):
    """Асинхронный запуск парсера и отправка данных в БД."""
    max_id = str(message.from_user.id)
    user = db.get_user(max_id)
    
    if not user or not user['login'] or not user['password']:
        await message.answer("❌ Сначала укажи логин и пароль в **👤 Мой профиль**!")
        return
        
    status_msg = await message.answer("🔄 Подключаюсь к ЛК ГУАП и забираю задания...")
    
    try:
        # Устанавливаем учетные данные в модуле авторизации парсера
        auth.LOGIN = user['login']
        auth.PASSWORD = user['password']
        
        # Запускаем парсинг в асинхронном режиме, чтобы бот не «замерзал»
        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(None, auth.login)
        tasks = await loop.run_in_executor(None, guap_parser.get_tasks, session)
        
        if not tasks:
            await status_msg.edit_text("👍 Новых или активных заданий не найдено!")
            return
            
        # Формируем структуру под sync_assignments
        grouped_data = {}
        for task in tasks:
            subject = task['subject']
            if subject not in grouped_data:
                grouped_data[subject] = {
                    "name": subject,
                    "teacher": task['teacher'],
                    "assignments": []
                }
            
            db_ready_deadline = normalize_deadline(task['deadline'])
            grouped_data[subject]["assignments"].append({
                "title": f"Задание №{task['number']}: {task['task']}",
                "deadline": db_ready_deadline,
                "source_id": str(task['number'])
            })
            
        disciplines_list = list(grouped_data.values())
        
        # Синхронизируем, используя внутренний ID
        sync_result = db.sync_assignments(user['id'], disciplines_list)
        
        await status_msg.edit_text(
            f"✅ *Синхронизация успешна!*\n\n"
            f"➕ Новых заданий: *{sync_result['added']}*\n"
            f"🔄 Обновлено статусов: *{sync_result['updated']}*"
        , parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка при синхронизации: {e}")
        await status_msg.edit_text("❌ Ошибка авторизации в ГУАП. Проверь данные в профиле.")


# ================= ПРИВЯЗКА ДАННЫХ (ЛОГИН:ПАРОЛЬ) =================

@dp.message(F.text.contains(":"))
async def handle_credentials_input(message: types.Message):
    """
    Пункт 4 инструкции: сохранение логина и пароля.
    Решает проблему INSERT OR IGNORE при обновлении данных.
    """
    max_id = str(message.from_user.id)
    
    try:
        # Делим строго по первому двоеточию, убирая лишние пробелы по бокам
        parts = message.text.split(":", 1)
        if len(parts) < 2:
            raise ValueError
        login_part = parts[0].strip()
        password_part = parts[1].strip()
    except Exception:
        await message.answer("❌ Ошибка! Формат должен быть строго: `логин:пароль`", parse_mode="Markdown")
        return
        
    # 1. Пытаемся вызвать оригинальный метод напарника (если юзера нет)
    db.add_user(max_id, login_part, password_part)
    
    # 2. Обходим баг INSERT OR IGNORE: принудительно перезаписываем данные
    try:
        # Обновляем пароль встроенным методом
        db.update_user_password(max_id, password_part)
        
        # Логин обновляем напрямую в БД через коннектор (так как у напарника нет метода update_user_login)
        conn = db.get_connection()
        conn.execute("UPDATE users SET login = ? WHERE user_id = ?", (login_part, max_id))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Данные успешно сохранены!\n\n"
            f"👤 *Логин:* `{login_part}`\n"
            f"🔑 *Пароль:* `••••••••`\n\n"
            f"Теперь нажми кнопку **🔄 Синхронизировать ЛК**.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await message.answer("❌ Произошла ошибка базы данных при сохранении.")


# ================= CALLBACKS =================

@dp.callback_query(F.data == "delete_account")
async def callback_delete_account(callback: types.CallbackQuery):
    """Удаление аккаунта."""
    max_id = str(callback.from_user.id)
    if db.delete_user(max_id):
        await callback.message.edit_text("❌ Профиль деактивирован. Для возвращения напиши /start.")
        await callback.answer("Успешно")
    else:
        await callback.answer("Ошибка БД", show_alert=True)


# ================= ЗАПУСК =================

async def main():
    logger.info("Запуск бота...")
    db.init_db()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
