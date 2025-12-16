import asyncio
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ ===
TOKEN = "8514017811:AAEK007dilGv0Etcvxp2HJhEMQ5npt22pps"
ADMINS = [724545647, 8390126598]  
CHANNEL_ID = "@blackrussia_85"

bot = Bot(token=TOKEN)
dp = Dispatcher()

PENDING_FILE = "pending.json"
LOCK = asyncio.Lock()

# === ЗАГРУЗКА / СОХРАНЕНИЕ ОЖИДАЮЩИХ ===
async def load_pending():
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

async def save_pending(data):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# === КЛАВИАТУРА ПОЛЬЗОВАТЕЛЯ ===
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Опубликовать объявление")],
        [KeyboardButton(text="📖 Помощь"), KeyboardButton(text="📞 Связь с админом")]
    ],
    resize_keyboard=True
)

# === /start ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Здесь ты можешь подать объявление, которое администратор проверит перед публикацией в канале.",
        reply_markup=user_kb
    )

# === КНОПКА «Помощь» ===
@dp.message(F.text.in_(["📖 Помощь", "Помощь"]))
async def help_msg(message: types.Message):
    await message.answer(
        "📘 *Пример подачи объявления:*\n\n"
        "1️⃣ Куплю/Продам —\n"
        "2️⃣ Цена —\n"
        "3️⃣ Связь — @вашюзер\n\n"
        "После этого отправь сообщение боту, и админ проверит его.",
        parse_mode="Markdown"
    )

# === КНОПКА «Связь с админом» ===
@dp.message(F.text.in_(["📞 Связь с админом", "Связь с админом"]))
async def contact_admin(message: types.Message):
    await message.answer("📬 Для связи с администратором напиши: @onesever")

# === КНОПКА «Опубликовать объявление» ===
@dp.message(F.text.in_(["📢 Опубликовать объявление", "Опубликовать объявление"]))
async def publish_info(message: types.Message):
    await message.answer(
        "📝 Чтобы опубликовать объявление, отправь его сюда в виде текста, фото, видео или документа.\n\n"
        "📘 *Пример:*\n"
        "1️⃣ Куплю/Продам —\n"
        "2️⃣ Цена —\n"
        "3️⃣ Связь — @вашюзер",
        parse_mode="Markdown"
    )

# === ПОЛУЧЕНИЕ ОБЪЯВЛЕНИЙ ===
@dp.message()
async def handle_message(message: types.Message):
    # игнорируем кнопки
    if message.text in [
        "📢 Опубликовать объявление", "Опубликовать объявление",
        "📖 Помощь", "Помощь",
        "📞 Связь с админом", "Связь с админом"
    ]:
        return

    payload = {
        "from_id": message.from_user.id,
        "from_name": message.from_user.full_name,
        "from_username": message.from_user.username,
        "type": None,
        "text": None,
        "file_id": None,
        "caption": None,
    }

    if message.photo:
        payload["type"] = "photo"
        payload["file_id"] = message.photo[-1].file_id
        payload["caption"] = message.caption or ""
    elif message.video:
        payload["type"] = "video"
        payload["file_id"] = message.video.file_id
        payload["caption"] = message.caption or ""
    elif message.document:
        payload["type"] = "document"
        payload["file_id"] = message.document.file_id
        payload["caption"] = message.caption or ""
    elif message.text:
        payload["type"] = "text"
        payload["text"] = message.text
    else:
        await message.answer("❌ Тип сообщения не поддерживается.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data="reject")]
    ])

    # отправляем админу
    if payload["type"] == "photo":
        sent = await bot.send_photo(
            ADMIN_ID, payload["file_id"],
            caption=f"🆕 Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['caption']}",
            reply_markup=kb
        )
    elif payload["type"] == "video":
        sent = await bot.send_video(
            ADMIN_ID, payload["file_id"],
            caption=f"🆕 Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['caption']}",
            reply_markup=kb
        )
    elif payload["type"] == "document":
        sent = await bot.send_document(
            ADMIN_ID, payload["file_id"],
            caption=f"🆕 Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['caption']}",
            reply_markup=kb
        )
    else:
        sent = await bot.send_message(
            ADMIN_ID,
            f"🆕 Объявление от {payload['from_name']} (@{payload['from_username']})\n\n{payload['text']}",
            reply_markup=kb
        )

    async with LOCK:
        pending = await load_pending()
        pending[str(sent.message_id)] = payload
        await save_pending(pending)

    await message.answer("✅ Ваше объявление отправлено на модерацию!", reply_markup=user_kb)

# === ОБРАБОТКА КНОПОК ===
@dp.callback_query(F.data.in_(["approve", "reject"]))
async def moderation(query: types.CallbackQuery):
    action = query.data
    msg_id = str(query.message.message_id)

    if query.from_user.id != ADMIN_ID:
        await query.answer("Недостаточно прав ❌", show_alert=True)
        return

    async with LOCK:
        pending = await load_pending()
        payload = pending.pop(msg_id, None)
        await save_pending(pending)

    if not payload:
        await query.answer("⚠️ Уже обработано.")
        return

    if action == "approve":
        # публикуем в канал
        if payload["type"] == "photo":
            await bot.send_photo(CHANNEL_ID, payload["file_id"], caption=payload["caption"])
        elif payload["type"] == "video":
            await bot.send_video(CHANNEL_ID, payload["file_id"], caption=payload["caption"])
        elif payload["type"] == "document":
            await bot.send_document(CHANNEL_ID, payload["file_id"], caption=payload["caption"])
        else:
            await bot.send_message(CHANNEL_ID, payload["text"])

        await bot.send_message(payload["from_id"], "✅ Ваше объявление опубликовано!")
        await query.answer("✅ Опубликовано!")
    else:
        await bot.send_message(payload["from_id"], "❌ Ваше объявление отклонено.")
        await query.answer("❌ Отклонено!")

    await bot.edit_message_reply_markup(chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=None)

# === ЗАПУСК ===
async def main():
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

