from datetime import datetime, timedelta
from typing import Iterable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from modal import App, Image, Secret, Function, Dict, web_endpoint
import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO)

app = App("trending-stocks")

auth_scheme = HTTPBearer()

get_ddgs_news = Function.lookup("ddgs-news", "get_ddgs_news")
get_options = Function.lookup("get-options", "get_options")

tickers_dict = Dict.from_name("tickers-data", create_if_missing=True)


def sort_stocks(data, key):
    return sorted(data, key=lambda item: item[key], reverse=True)


async def check_ticker(ticker):
    import yfinance as yf

    return ticker if yf.Ticker(ticker).info.get("symbol") else None


async def filter_valid_tickers(tickers: Iterable[str]) -> Iterable[str]:
    valid_tickers = await asyncio.gather(*(check_ticker(ticker) for ticker in tickers))
    return [ticker for ticker in valid_tickers if ticker is not None]


@app.function(image=Image.debian_slim().pip_install("httpx", "yfinance"))
async def get_top_trending_tickers(
    num_stocks: int, filter: str = "wallstreetbets"
) -> Iterable[str]:
    """
    Get the top trending stocks from ApeWisdom
    """
    import httpx

    url = f"https://apewisdom.io/api/v1.0/filter/{filter}"

    try:
        if (
            tickers_dict["trending"]
            and len(tickers_dict["trending"]) >= num_stocks
            and datetime.now() - tickers_dict["last_updated"] < timedelta(hours=1)
        ):
            logging.info("Loaded from dict.")
            return tickers_dict["trending"][:num_stocks]
    except KeyError:
        logging.info("No cached result found.")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        raise e

    most_upvoted = sort_stocks(data["results"], "upvotes")[:num_stocks]
    most_mentions = sort_stocks(data["results"], "mentions")[:num_stocks]

    top_trending_tickers = {stock["ticker"] for stock in most_upvoted + most_mentions}
    top_trending_tickers = await filter_valid_tickers(top_trending_tickers)

    # save to dict
    tickers_dict["trending"] = top_trending_tickers
    tickers_dict["last_updated"] = datetime.now()

    return top_trending_tickers


@app.function(image=Image.debian_slim().pip_install("yfinance"))
def get_trending_stocks_and_news(
    num_stocks: int = 6,
) -> list[tuple[str, list[dict], list[dict]]]:
    import yfinance as yf

    tickers = get_top_trending_tickers.remote(num_stocks)
    ticker_desc = [yf.Ticker(ticker).info.get("shortName") for ticker in tickers]
    news = list(get_ddgs_news.map(tickers, ticker_desc))
    options = list(get_options.map(tickers))

    return list(zip(tickers, news, options))


@app.function(secrets=[Secret.from_name("auth-token")])
@web_endpoint()
def endpoint(
    num_stocks: int = 6, token: HTTPAuthorizationCredentials = Depends(auth_scheme)
) -> list[tuple[str, list[dict], list[dict]]]:
    if token.credentials != os.environ["AUTH_TOKEN"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return get_trending_stocks_and_news.remote(num_stocks)


@app.local_entrypoint()
async def local():
    print(get_top_trending_tickers.remote(10))
