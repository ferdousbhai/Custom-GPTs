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

trending_stocks_and_news_results = Dict.from_name(
    "trending_stocks_and_news_results", create_if_missing=True
)


@app.function(image=httpx_image)
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

    return [stock["ticker"] for stock in trending_stocks]


@app.function(
    image=yfinance_image,
    secrets=[Secret.from_name("auth-token")],
)
@web_endpoint()
def get_trending_stocks_and_news(
    num_stocks: int = 6, token: HTTPAuthorizationCredentials = Depends(auth_scheme)
) -> list[tuple[str, list[dict]]]:
    """
    Get the top news for each ticker
    """
    from time import time
    import yfinance as yf

    if token.credentials != os.environ["AUTH_TOKEN"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # check if cached result is valid
    result = trending_stocks_and_news_results.get("trending_stocks_and_news")
    if result and time() - result["updated_at"] < 600:
        logging.info("Loaded from cache.")
        return result["data"]

    tickers: list[str] | None = get_top_trending_tickers.remote(num_stocks)
    if tickers is None:
        raise ValueError("No tickers found")

    ticker_desc = [yf.Ticker(ticker).info.get("shortName") for ticker in tickers]

    list_of_ticker_news = list(ddgs_news.map(tickers, ticker_desc))

    logging.info(list_of_ticker_news)

    # save to dict
    trending_stocks_and_news_results["trending_stocks_and_news"] = {
        "updated_at": time(),
        "data": list_of_ticker_news,
    }
    logging.info("Saved to volume.")

    return list_of_ticker_news
