from modal import App, Image, Secret, Function, Dict, web_endpoint
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import logging


logging.basicConfig(level=logging.INFO)

app = App("trending-stocks")

httpx_image = Image.debian_slim(python_version="3.12").run_commands("pip install httpx")

yfinance_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install yfinance httpx"
)

auth_scheme = HTTPBearer()

ddgs_news = Function.lookup("ddgs-news", "ddgs_news")
get_options = Function.lookup("get-options", "get_options")

trending_stocks_and_news_result = Dict.from_name(
    "trending_stocks_and_news_result", create_if_missing=True
)


@app.function(image=httpx_image)
async def get_top_trending_tickers(
    num_stocks: int, filter: str = "wallstreetbets"
) -> list[str] | None:
    """
    Get the top trending stocks from ApeWisdom
    """
    import httpx

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

    return [stock["ticker"] for stock in trending_stocks]


@app.function(
    image=yfinance_image,
    secrets=[Secret.from_name("auth-token")],
)
@web_endpoint()
def get_trending_stocks_and_news(
    num_stocks: int = 6, token: HTTPAuthorizationCredentials = Depends(auth_scheme)
) -> tuple[list[tuple[str, list[dict]]], str]:
    """
    Get the top news for each ticker
    """
    from time import time
    from datetime import datetime
    import yfinance as yf

    if token.credentials != os.environ["AUTH_TOKEN"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # check if cached result is valid
    result_data = trending_stocks_and_news_result.get("data")
    updated_at = trending_stocks_and_news_result.get("updated_at")
    if result_data and time() - updated_at < 600:
        logging.info(f"Loaded from dict. \n{result_data}")
        return (
            result_data,
            f"Last updated: {datetime.fromtimestamp(updated_at).strftime('%Y-%m-%d %H:%M')}",
        )

    # get tickers, news, and options
    tickers: list[str] | None = get_top_trending_tickers.remote(num_stocks)
    logging.info(f"Tickers: {tickers}")
    if tickers is None:
        raise ValueError("No tickers found")
    ticker_desc = [yf.Ticker(ticker).info.get("shortName") for ticker in tickers]
    news: list[list[dict]] = list(ddgs_news.map(tickers, ticker_desc))
    options: list[list[dict]] = list(get_options.map(tickers))

    # zip the tickers, news, and options
    ticker_news_options_pairs = list(zip(tickers, news, options))
    logging.info(f"Ticker news pairs:\n{ticker_news_options_pairs}")

    # save to dict
    trending_stocks_and_news_result["data"] = ticker_news_options_pairs
    timestamp = time()
    trending_stocks_and_news_result["updated_at"] = timestamp
    logging.info("Saved to dict.")

    return (
        ticker_news_options_pairs,
        f"Current time: {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')}",
    )
