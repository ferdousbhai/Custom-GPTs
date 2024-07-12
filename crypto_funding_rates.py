import modal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("crypto-funding-rates")

send_message = modal.Function.lookup("send-message-to-tg-channel", "send_message")

websockets_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install websockets"]
)


@app.function(image=websockets_image)
async def get_funding_rate(ticker: str) -> float:
    import websockets
    import json

    msg = {
        "jsonrpc": "2.0",
        "method": "public/get_funding_chart_data",
        "id": 42,
        "params": {"instrument_name": f"{ticker}-PERPETUAL", "length": "8h"},
    }
    async with websockets.connect("wss://test.deribit.com/ws/api/v2") as websocket:
        await websocket.send(json.dumps(msg))
        response = await websocket.recv()
        data = json.loads(response)
        funding_rate = data["result"]["current_interest"]
        logging.info(f"{ticker} funding rate: {funding_rate:.4%}")
        if funding_rate < 0:
            send_message.remote(
                f"{ticker}-PERP funding rate is negative: {funding_rate:.4%}"
            )


@app.function(schedule=modal.Period(days=1))
def main():
    list(get_funding_rate.map(["BTC", "ETH"]))
