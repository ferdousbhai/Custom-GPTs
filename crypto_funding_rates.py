import os
import modal
import logging
import json


logging.basicConfig(level=logging.INFO)

app = modal.App("crypto-funding-rates")

send_message = modal.Function.lookup("send-message-to-tg-channel", "send_message")

websockets_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install websockets"]
)

WEBSOCKET_URL = "wss://test.deribit.com/ws/api/v2"
SCHEDULE_TIME = "0 9 * * *"  # 9am (UTC)


def create_message(ticker: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "public/get_funding_chart_data",
        "id": 42,
        "params": {"instrument_name": f"{ticker}-PERPETUAL", "length": "8h"},
    }


@app.function(image=websockets_image, secrets=[modal.Secret.from_name("telegram")])
async def get_funding_rate(ticker: str) -> float | None:
    import websockets

    msg = create_message(ticker)
    try:
        async with websockets.connect(WEBSOCKET_URL) as websocket:
            await websocket.send(json.dumps(msg))
            response = await websocket.recv()
            data = json.loads(response)
            funding_rate = data["result"]["current_interest"]
            logging.info(f"{ticker} funding rate: {funding_rate:.4%}")
            if funding_rate < 0:
                send_message.spawn(
                    bot_token=os.environ["ASK_DAN_BOT_TOKEN"],
                    chat_id=int(os.environ["LONG_VOL_CHANNEL_CHAT_ID"]),
                    text=f"🔔 {ticker}-PERP funding rate is negative: {funding_rate:.4%}.",
                )
            return funding_rate
    except (websockets.WebSocketException, json.JSONDecodeError) as e:
        logging.error(f"Error fetching funding rate for {ticker}: {e}")
        return None


@app.function(schedule=modal.Cron(SCHEDULE_TIME))
def main():
    list(get_funding_rate.map(["BTC", "ETH"]))


# testing
@app.local_entrypoint()
def test():
    get_funding_rate.remote("BTC")
