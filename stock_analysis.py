import os
import logging
from datetime import datetime, timedelta

from modal import App, Image, Secret, Function, Dict, web_endpoint
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


logging.basicConfig(level=logging.INFO)

app = App("stock-analysis")

image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install httpx yfinance"
)

stock_analysis_dict = Dict.from_name("stock-analysis-data", create_if_missing=True)

auth_scheme = HTTPBearer()

get_ddgs_news = Function.lookup("ddgs-news", "get_ddgs_news")
get_options = Function.lookup("get-options", "get_options")


@app.function(image=image, keep_warm=1)
async def generate_investment_report(ticker_to_research: str) -> dict:
    """
    Generate an investment report for a given ticker.
    This function generates a report with the following sections:
    - Ticker Info
    - Latest News
    - Analyst Recommendations
    - Upgrades/Downgrades
    - Options
    The data is pulled from yfinance and ddgs.
    """
    import yfinance as yf

    logging.info(f"Generating report for: {ticker_to_research}")

    # Ticker object
    ticker = yf.Ticker(ticker_to_research)

    result = {}

    # Get ticker info from yfinance
    if ticker.info:
        result["tickerInfo"] = ticker.info

    # Get news from ddgs
    ticker_news_list = await get_ddgs_news.remote.aio(
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
    options: list[list[dict]] = get_options.remote(ticker_to_research)
    if options:
        logging.info("Fetched options")
        result["options"] = options

    logging.info(f"Generated report for {ticker_to_research}")
    return result


@app.function(secrets=[Secret.from_name("auth-token")], keep_warm=1)
@web_endpoint()
async def endpoint(
    ticker_to_research: str, token: HTTPAuthorizationCredentials = Depends(auth_scheme)
) -> dict:
    if token.credentials != os.environ["AUTH_TOKEN"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if ticker_to_research not in stock_analysis_dict:
        stock_analysis_dict[ticker_to_research] = {"report": None, "timestamp": None}

    if (
        stock_analysis_dict[ticker_to_research]["report"] is None
        or stock_analysis_dict[ticker_to_research]["timestamp"] is None
        or datetime.now() - stock_analysis_dict[ticker_to_research]["timestamp"]
        > timedelta(minutes=10)
    ):
        stock_analysis_dict[ticker_to_research] = {
            "report": generate_investment_report.remote(ticker_to_research),
            "timestamp": datetime.now(),
        }
        logging.info(f"Updated report for {ticker_to_research}")

    return stock_analysis_dict[ticker_to_research]


@app.local_entrypoint()
def test():
    print(generate_investment_report.remote("AAPL"))
