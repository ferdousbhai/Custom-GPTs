import modal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("crypto-funding-rates")

send_message = modal.Function.lookup("send-message-to-tg-channel", "send_message")

websockets_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install websockets"]
)

funding_rate_results = modal.Dict.from_name(
    "funding-rate-results", create_if_missing=True
)


@app.function(image=websockets_image, schedule=modal.Period(days=1))
async def get_funding_rate(
    tickers: list[str] = ["BTC", "ETH"],
) -> tuple[float, float]:
    import websockets
    import json
    from datetime import datetime

    for ticker in tickers:
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
            logging.info(f"{ticker} funding rate data: {data}")
            funding_rate = data["result"]["current_interest"]
            funding_rate_results[ticker] = funding_rate
            if funding_rate < 0:
                send_message.remote(
                    f"{ticker}-PERP funding rate is negative: {funding_rate:.4%}"
                )

    funding_rate_results["last_checked"] = datetime.now().isoformat()
    return tuple(funding_rate_results.get(ticker) for ticker in tickers)


@app.local_entrypoint()
def main():
    print(get_funding_rate.remote())
