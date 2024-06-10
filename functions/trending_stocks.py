from modal import App, Image, web_endpoint
from .common import gpt_data_vol, ddgs_news
import logging

logging.basicConfig(level=logging.INFO)

app = App("trending-stocks")

httpx_image = Image.debian_slim(python_version="3.12").run_commands("pip install httpx")

yfinance_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install yfinance httpx"
)


@app.function(image=httpx_image, volumes={"/data": gpt_data_vol})
async def get_top_trending_tickers(num_stocks: int) -> list[str] | None:
    """
    Get the top trending stocks from ApeWisdom
    """
    import httpx

    filter = "wallstreetbets"
    url = f"https://apewisdom.io/api/v1.0/filter/{filter}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.RequestError as e:
        logging.error(f"Request failed: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error occurred: {e}")
        return None
    except ValueError:
        logging.error("Failed to decode JSON")
        return None

    def sort_stocks(data, key, num_stocks):
        return sorted(data, key=lambda item: item[key], reverse=True)[:num_stocks]

    most_upvoted = sort_stocks(data["results"], "upvotes", num_stocks)
    most_mentions = sort_stocks(data["results"], "mentions", num_stocks)

    trending_stocks = {
        item["ticker"]: item for item in most_upvoted + most_mentions
    }.values()

    # log
    report = "#Trending Stonks:"
    for stock in trending_stocks:
        report += f"\n{stock['ticker']} ({stock['name']}) was mentioned {stock['mentions']} times with {stock['upvotes']} upvotes. It was mentioned {stock['mentions_24h_ago']} times 24h ago."
    logging.info(report)

    # return the "ticker" values as a list of strings
    return [stock["ticker"] for stock in trending_stocks]


@app.function(image=yfinance_image, volumes={"/data": gpt_data_vol})
@web_endpoint()
async def get_trending_stocks_and_news(
    num_stocks: int = 6,
) -> list[tuple[str, list[dict]]]:
    """
    Get the top news for each ticker
    """
    import asyncio
    import os
    from time import time
    import pickle
    import yfinance as yf

    def load_from_pickle(
        filename: str = "/data/trending_stocks.pkl", expiration_time: int = 600
    ) -> list[tuple[str, list[dict]]] | None:
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                file_content = pickle.load(f)
                data = file_content.get("data")
                timestamp = file_content.get("timestamp")
                if time() - timestamp < expiration_time:
                    return data
        return None

    def save_to_pickle(data, filename: str = "/data/trending_stocks.pkl"):
        with open(filename, "wb") as f:
            pickle.dump({"timestamp": time(), "data": data}, f)
        gpt_data_vol.commit()

    list_of_ticker_news: list[tuple[str, list[dict]]] | None = load_from_pickle()

    if list_of_ticker_news:
        logging.info(f"Loaded from pickle:\n{list_of_ticker_news}")
        return list_of_ticker_news

    tickers: list[str] | None = get_top_trending_tickers.remote(num_stocks)
    if tickers is None:
        raise ValueError("No tickers found")

    async def fetch_news_for_ticker(ticker):
        ticker_news = ddgs_news.remote(ticker, yf.Ticker(ticker).info.get("shortName"))
        return (ticker, ticker_news)

    list_of_ticker_news = await asyncio.gather(
        *(fetch_news_for_ticker(ticker) for ticker in tickers)
    )

    logging.info(list_of_ticker_news)

    save_to_pickle(list_of_ticker_news)
    logging.info("Saved to volume.")

    return list_of_ticker_news
