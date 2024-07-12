import modal
import os

app = modal.App("send-message-to-tg-channel")

telegram_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install python-telegram-bot"]
)


@app.function(image=telegram_image, secrets=[modal.Secret.from_name("telegram")])
async def send_message(text: str, channel_id: int | None = None):
    from telegram import Bot

    if channel_id is None:
        channel_id = int(os.environ["LONG_VOL_CHANNEL_CHAT_ID"])

    async with Bot(os.environ["ASK_DAN_BOT_TOKEN"]) as bot:
        await bot.send_message(text=text, chat_id=channel_id)
