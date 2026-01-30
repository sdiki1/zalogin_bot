import logging
from html import escape
from typing import Set

from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import load_config
from app.db import (
    init_db,
    get_access_code,
    set_access_code,
    upsert_user,
    record_login,
    list_users,
    list_logins,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


ADMIN_SET_CODE = "admin_set_code"
ADMIN_LIST_USERS = "admin_list_users"
ADMIN_LIST_LOGINS = "admin_list_logins"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("Отправить контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        "🌙 Для ночного доступа в прачечную самообслуживания отправьте свой контакт кнопкой ниже — "
        "в ответ придёт код доступа. 🔐\n"
        "Введите его на кодовой панели у двери прачечной. 🧺",
        reply_markup=keyboard,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Команды:\n"
        "/start — отправить контакт\n"
        "/admin — админ-панель (для админов)",
    )


def _is_admin(user_id: int, admin_ids: Set[int]) -> bool:
    return user_id in admin_ids


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.contact is None:
        return

    contact = message.contact
    from_user = message.from_user

    if from_user is None or contact.user_id != from_user.id:
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("Отправить контакт", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.reply_text(
            "Пожалуйста, отправьте свой контакт кнопкой ниже.",
            reply_markup=keyboard,
        )
        return

    config = context.application.bot_data["config"]
    user_id = upsert_user(
        config.db_path,
        tg_id=from_user.id,
        phone=contact.phone_number or "",
        full_name=(from_user.full_name or "").strip(),
        username=(from_user.username or "") if from_user.username else "",
    )
    record_login(config.db_path, user_id)

    code = get_access_code(config.db_path)
    await message.reply_text(
        f"{escape(code)}\n\n🌱Код периодически меняется, если в будущем он у вас не сработает, в данном чат-боте зайдите в меню ниже и снова запросите новый код.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    config = context.application.bot_data["config"]
    if user is None or not _is_admin(user.id, config.admin_ids):
        await update.message.reply_text("Доступ запрещён.")
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Изменить код", callback_data=ADMIN_SET_CODE)],
            [InlineKeyboardButton("Список пользователей", callback_data=ADMIN_LIST_USERS)],
            [InlineKeyboardButton("История входов", callback_data=ADMIN_LIST_LOGINS)],
        ]
    )
    await update.message.reply_text("Админ-панель:", reply_markup=keyboard)


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    user = query.from_user
    config = context.application.bot_data["config"]
    if user is None or not _is_admin(user.id, config.admin_ids):
        await query.answer("Доступ запрещён.", show_alert=True)
        return

    await query.answer()

    if query.data == ADMIN_SET_CODE:
        awaiting = context.application.bot_data.setdefault("awaiting_code", set())
        awaiting.add(user.id)
        await query.message.reply_text("Отправьте новый код одним сообщением.")
        return

    if query.data == ADMIN_LIST_USERS:
        rows = list_users(config.db_path, limit=50)
        if not rows:
            await query.message.reply_text("Пользователей пока нет.")
            return
        lines = ["Последние пользователи:"]
        for idx, row in enumerate(rows, start=1):
            username = f"@{row['username']}" if row["username"] else "—"
            phone = row["phone"] or "—"
            full_name = row["full_name"] or "—"
            lines.append(
                f"{idx}. {full_name} ({username}), {phone}, id:{row['tg_id']}"
            )
        await query.message.reply_text("\n".join(lines))
        return

    if query.data == ADMIN_LIST_LOGINS:
        rows = list_logins(config.db_path, limit=50)
        if not rows:
            await query.message.reply_text("История входов пуста.")
            return
        lines = ["Последние входы (UTC):"]
        for idx, row in enumerate(rows, start=1):
            username = f"@{row['username']}" if row["username"] else "—"
            phone = row["phone"] or "—"
            full_name = row["full_name"] or "—"
            lines.append(
                f"{idx}. {row['ts']} — {full_name} ({username}), {phone}, id:{row['tg_id']}"
            )
        await query.message.reply_text("\n".join(lines))
        return


async def admin_set_code_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    user = message.from_user
    if user is None:
        return

    config = context.application.bot_data["config"]
    if not _is_admin(user.id, config.admin_ids):
        return

    awaiting = context.application.bot_data.get("awaiting_code", set())
    if user.id not in awaiting:
        return

    code = (message.text or "").strip()
    if not code:
        await message.reply_text("Код не может быть пустым. Отправьте новый код.")
        return

    set_access_code(config.db_path, code)
    awaiting.remove(user.id)
    await message.reply_text(f"Код обновлён: {escape(code)}")


async def admin_set_code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    user = message.from_user
    if user is None:
        return

    config = context.application.bot_data["config"]
    if not _is_admin(user.id, config.admin_ids):
        await message.reply_text("Доступ запрещён.")
        return

    args = context.args
    if not args:
        await message.reply_text("Использование: /setcode <новый_код>")
        return

    code = " ".join(args).strip()
    if not code:
        await message.reply_text("Код не может быть пустым.")
        return

    set_access_code(config.db_path, code)
    await message.reply_text(f"Код обновлён: {escape(code)}")


def build_app() -> Application:
    config = load_config()
    init_db(config.db_path, config.default_access_code)

    application = Application.builder().token(config.bot_token).build()
    application.bot_data["config"] = config
    application.bot_data["awaiting_code"] = set()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("setcode", admin_set_code_cmd))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_code_text)
    )

    return application


def main() -> None:
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
