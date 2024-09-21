from modal import App, Image, Secret
import logging

logging.basicConfig(level=logging.INFO)

app = App("crypto-funding-rates")


@app.function(
    image=Image.debian_slim(python_version="3.12").pip_install("websockets"),
    secrets=[Secret.from_name("telegram")],
)
async def get_crypto_funding_rates(ticker: str) -> float | None:
    import websockets
    import json

    try:
        async with websockets.connect("wss://test.deribit.com/ws/api/v2") as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "public/get_funding_chart_data",
                        "id": 42,
                        "params": {
                            "instrument_name": f"{ticker}-PERPETUAL",
                            "length": "8h",
                        },
                    }
                )
            )
            data = json.loads(await websocket.recv())
            funding_rate = data["result"]["current_interest"]
            logging.info(f"{ticker} funding rate: {funding_rate:.4%}")
            return funding_rate
    except (websockets.WebSocketException, json.JSONDecodeError) as e:
        logging.error(f"Error fetching funding rate for {ticker}: {e}")
        return None


# testing
@app.local_entrypoint()
def test():
    funding_rate = get_crypto_funding_rates.remote("BTC")
    print(f"Funding rate: {funding_rate}")
    print(f"Type: {type(funding_rate)}")
