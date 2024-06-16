from modal import App, Image, Secret, Function, web_endpoint
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import logging

logging.basicConfig(level=logging.INFO)

app = App("stock-analysis")

finance_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install httpx yfinance tabulate"
)

auth_scheme = HTTPBearer()

ddgs_news = Function.lookup("ddgs-news", "ddgs_news")
get_options = Function.lookup("get-options", "get_options")


@app.function(image=finance_image, secrets=[Secret.from_name("auth-token")])
@web_endpoint()
async def generate_investment_report(
    ticker_to_research: str, token: HTTPAuthorizationCredentials = Depends(auth_scheme)
) -> tuple[dict, str]:
    """
    Generate an investment report for a given ticker.
    This function generates a report with the following sections:
    - Ticker Info
    - Latest News
    - Analyst Recommendations
    - Upgrades/Downgrades
    The data is pulled from yfinance and ddgs.
    """
    import yfinance as yf
    from datetime import datetime
    from time import time

    if token.credentials != os.environ["AUTH_TOKEN"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logging.info(f"Generating report for: {ticker_to_research}")

    # Ticker object
    ticker = yf.Ticker(ticker_to_research)

    result = {}

    # Get ticker info from yfinance
    if ticker.info:
        result["tickerInfo"] = ticker.info

    # Get news from ddgs
    ticker_news_list = await ddgs_news.remote.aio(
        ticker_to_research, ticker.info.get("shortName")
    )
    if ticker_news_list:
        logging.info("Fetched news")
        result["latest_news"] = ticker_news_list

    # Get analyst recommendations from yfinance
    if not ticker.recommendations.empty:  # recommendations is a DataFrame
        logging.info("Fetched analyst recommendations")
        result["analyst_recommendations"] = ticker.recommendations.to_json()

    # Get upgrades and downgrades from yfinance
    if not ticker.upgrades_downgrades.empty:  # upgrades_downgrades is a DataFrame
        logging.info("Fetched upgrades and downgrades")
        result["upgrades_downgrades"] = ticker.upgrades_downgrades.head(20).to_json()

    # Get options
    options: list[list[dict]] = get_options.remote(ticker_to_research, num_options=6)
    if options:
        logging.info("Fetched options")
        result["options"] = options

    logging.info(f"Generated report for ticker: {ticker_to_research}:\n{result}")
    return (
        result,
        f"Current time: {datetime.fromtimestamp(time()).strftime('%Y-%m-%d %H:%M')}",
    )
