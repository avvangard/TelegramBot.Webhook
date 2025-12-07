import os
import json
from contextlib import asynccontextmanager
from http import HTTPStatus
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

# ---- ENV ----
load_dotenv()
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_DOMAIN: str = os.getenv("RAILWAY_PUBLIC_DOMAIN")

# ---- STORAGE ----
DB_PATH = "db.json"

def load_db():
    if not os.path.exists(DB_PATH):
        return {"users": {}, "registered": {}}
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=4)


# ---- TELEGRAM BOT ----
bot_builder = (
    Application.builder()
    .token(TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bot_builder.bot.setWebhook(url=f"{WEBHOOK_DOMAIN}")
    async with bot_builder:
        await bot_builder.start()
        yield
        await bot_builder.stop()


app = FastAPI(lifespan=lifespan)


@app.post("/")
async def process_update(request: Request):
    message = await request.json()
    update = Update.de_json(message, bot_builder.bot)
    await bot_builder.process_update(update)
    return Response(status_code=HTTPStatus.OK)


# ---- TELEGRAM HANDLERS ----
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋\n"
        "Чтобы получить доступ — зарегистрируйся на платформе\n"
        "и отправь мне свой ID трейдера:"
    )

    db = load_db()
    db["users"][str(update.effective_user.id)] = {
        "status": "waiting_id"
    }
    save_db(db)


async def handle_id(update: Update, _: ContextTypes.DEFAULT_TYPE):
    tg_user = str(update.effective_user.id)
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("ID должен быть числом.")
        return

    db = load_db()

    db["users"][tg_user] = {
        "status": "waiting_reg",
        "entered_id": text
    }
    save_db(db)

    await update.message.reply_text(
        "Окей! 👍\n"
        "Жду подтверждения от платформы…"
    )


bot_builder.add_handler(CommandHandler("start", start))
bot_builder.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)
)


# ---- POSTBACK HANDLER ----
@app.get("/pocket/reg")
async def pocket_reg(click_id: str = None, trader_id: str = None):
    """
    GET-запрос от Pocket Option:
    /pocket/reg?click_id=xxx&trader_id=yyy
    """
    db = load_db()

    matched_user = None

    for tg_user, data in db["users"].items():
        if data.get("entered_id") == trader_id:
            matched_user = tg_user
            break

    if not matched_user:
        return {"status": "NO_MATCH"}

    # помечаем как зарегистрированного
    db["registered"][matched_user] = trader_id
    save_db(db)

    # уведомляем юзера
    await bot_builder.bot.send_message(
        chat_id=int(matched_user),
        text="🎉 Ты успешно зарегистрирован!\nДоступ открыт."
    )

    return {"status": "OK", "trader_id": trader_id}
