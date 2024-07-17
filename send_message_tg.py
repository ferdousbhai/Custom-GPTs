import modal
from utils.markdown_v2_formatter import convert_to_markdown_v2

app = modal.App("send-message-to-tg-channel")

telegram_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install python-telegram-bot"]
)


@app.function(image=telegram_image)
async def send_message(bot_token: str, chat_id: int, text: str):
    from telegram import Bot

    async with Bot(token=bot_token) as bot:
        await bot.send_message(
            chat_id=chat_id,
            text=convert_to_markdown_v2(text),
            parse_mode="MarkdownV2",
        )
