import os
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import exceptions
from aiogram import F

# Настройки из переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")   # например "@bu_rinok"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not TOKEN or not CHANNEL_ID or ADMIN_ID == 0:
    raise SystemExit("Нужны переменные окружения: TELEGRAM_TOKEN, CHANNEL_ID, ADMIN_ID")

bot = Bot(token=TOKEN)
dp = Dispatcher()

PENDING_FILE = "pending.json"
LOCK = asyncio.Lock()

# Помощники для сохранения/загрузки pending
async def load_pending():
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

async def save_pending(data):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# /start
@dp.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    await message.reply("Привет! Отправь сюда объявление (текст и/или фото). Оно пойдёт на модерацию.")

# Когда пользователь присылает сообщение (текст, фото, документ, видео)
@dp.message()
async def recv_post(message: types.Message):
    # составим payload, который достаточно для публикации
    payload = {
        "from_id": message.from_user.id,
        "from_name": message.from_user.full_name,
        "from_username": getattr(message.from_user, "username", None),
        "type": None,
        "text": None,
        "file_id": None,
        "caption": None,
    }

    # поддержка фото, документ, видео или просто текст
    if message.photo:
        payload["type"] = "photo"
        payload["file_id"] = message.photo[-1].file_id
        payload["caption"] = message.caption or message.text or ""
    elif message.document:
        payload["type"] = "document"
        payload["file_id"] = message.document.file_id
        payload["caption"] = message.caption or message.text or ""
    elif message.video:
        payload["type"] = "video"
        payload["file_id"] = message.video.file_id
        payload["caption"] = message.caption or message.text or ""
    elif message.text:
        payload["type"] = "text"
        payload["text"] = message.text
    else:
        await message.reply("Тип файла не поддерживается. Отправь фото, документ, видео или текст.")
        return

    # отправим админу — используем send_* чтобы получить message_id админского сообщения
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve:{id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data="reject:{id}")]
    ])

    try:
        if payload["type"] == "photo":
            sent = await bot.send_photo(
                ADMIN_ID,
                payload["file_id"],
                caption=f"Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['caption']}",
            )
        elif payload["type"] == "document":
            sent = await bot.send_document(
                ADMIN_ID,
                payload["file_id"],
                caption=f"Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['caption']}",
            )
        elif payload["type"] == "video":
            sent = await bot.send_video(
                ADMIN_ID,
                payload["file_id"],
                caption=f"Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['caption']}",
            )
        else:  # text
            sent = await bot.send_message(
                ADMIN_ID,
                f"Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['text']}",
            )
    except exceptions.BotBlocked:
        await message.reply("Ошибка: бот не может отправить сообщение администратору.")
        return
    except Exception as e:
        await message.reply(f"Ошибка при отправке на модерацию: {e}")
        return

    # Сохраняем payload в pending.json, ключ = message_id админа
    admin_msg_id = sent.message_id
    # обновим callback_data в сообщении админа (edit_reply_markup) — сначала подготовим kb с id
    kb_with_id = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{admin_msg_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{admin_msg_id}")]
    ])
    try:
        await bot.edit_message_reply_markup(chat_id=ADMIN_ID, message_id=admin_msg_id, reply_markup=kb_with_id)
    except Exception:
        pass  # не критично

    async with LOCK:
        pending = await load_pending()
        pending[str(admin_msg_id)] = payload
        await save_pending(pending)

    await message.reply("Ваше объявление отправлено на модерацию. Администратор примет решение.")

# Обработка нажатий кнопок
@dp.callback_query(F.data)
async def handle_callback(query: types.CallbackQuery):
    data = query.data  # формат approve:12345 или reject:12345
    parts = data.split(":")
    if len(parts) != 2:
        await query.answer("Некорректные данные.")
        return
    action, admin_msg_id = parts[0], parts[1]

    # Только админ может нажимать
    if query.from_user.id != ADMIN_ID:
        await query.answer("Только админ может принимать решения.", show_alert=True)
        return

    async with LOCK:
        pending = await load_pending()
        payload = pending.get(str(admin_msg_id))
        if not payload:
            await query.answer("Объявление не найдено или уже обработано.", show_alert=True)
            # убрать кнопки, если возможно
            try:
                await bot.edit_message_reply_markup(chat_id=ADMIN_ID, message_id=int(admin_msg_id), reply_markup=None)
            except Exception:
                pass
            return

        if action == "approve":
            # Публикуем в канал
            try:
                if payload["type"] == "photo":
                    await bot.send_photo(CHANNEL_ID, payload["file_id"], caption=payload.get("caption", ""))
                elif payload["type"] == "document":
                    await bot.send_document(CHANNEL_ID, payload["file_id"], caption=payload.get("caption", ""))
                elif payload["type"] == "video":
                    await bot.send_video(CHANNEL_ID, payload["file_id"], caption=payload.get("caption", ""))
                else:
                    text = payload.get("text") or ""
                    await bot.send_message(CHANNEL_ID, text)
                # Ответим админу
                await query.answer("✅ Опубликовано в канал.")
            except Exception as e:
                await query.answer(f"Ошибка при публикации: {e}", show_alert=True)
                return

        elif action == "reject":
            await query.answer("❌ Отклонено.")
        else:
            await query.answer("Неизвестное действие.")

        # Удалим запись из pending и уберём кнопки в админском сообщении
        pending.pop(str(admin_msg_id), None)
        await save_pending(pending)
        try:
            await bot.edit_message_reply_markup(chat_id=ADMIN_ID, message_id=int(admin_msg_id), reply_markup=None)
        except Exception:
            pass

if __name__ == "__main__":
    import asyncio

    async def main():
        await dp.start_polling(bot)

    asyncio.run(main())
 
    
