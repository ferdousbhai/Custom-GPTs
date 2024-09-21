from modal import App, Image

from utils.markdown_v2_formatter import convert_to_markdown_v2

app = App("send-message-to-tg")


@app.function(
    image=Image.debian_slim(python_version="3.12").pip_install("python-telegram-bot")
)
async def send_message(bot_token: str, chat_id: int, text: str):
    from telegram import Bot
    from telegram.error import TelegramError

    try:
        async with Bot(token=bot_token) as bot:
            await bot.send_message(
                chat_id=chat_id,
                text=convert_to_markdown_v2(text),
                parse_mode="MarkdownV2",
            )
    except TelegramError as e:
        print(f"Failed to send message: {e}")
