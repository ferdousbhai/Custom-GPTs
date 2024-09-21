import os
import logging
from datetime import datetime, timedelta

from modal import App, Image, Secret, Function, Dict, web_endpoint
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


logging.basicConfig(level=logging.INFO)

app = App("stock-analysis")
image = Image.debian_slim().pip_install("httpx", "yfinance")
stock_analysis_dict = Dict.from_name("stock-analysis-data", create_if_missing=True)
auth_scheme = HTTPBearer()

get_ddgs_news = Function.lookup("ddgs-news", "get_ddgs_news")
get_options = Function.lookup("get-options", "get_options")


@app.function(image=image)
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

    ticker = yf.Ticker(ticker_to_research)

    result = {"tickerInfo": ticker.info} if ticker.info else {}

    # Fetch news
    if news := await get_ddgs_news.remote.aio(
        ticker_to_research, ticker.info.get("shortName")
    ):
        logging.info("Fetched news")
        result["latest_news"] = news

    # Fetch recommendations
    for attr, key in [
        ("recommendations", "analyst_recommendations"),
        ("upgrades_downgrades", "upgrades_downgrades"),
    ]:
        df = getattr(ticker, attr)
        if not df.empty:
            logging.info(f"Fetched {key.replace('_', ' ')}")
            result[key] = df.head(20).to_dict(orient="records")

    # Fetch options
    if options := get_options.remote(ticker_to_research):
        logging.info("Fetched options")
        result["options"] = options

    logging.info(f"Generated report for {ticker_to_research}")
    return result


@app.function(secrets=[Secret.from_name("auth-token")])
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

    entry = stock_analysis_dict.setdefault(
        ticker_to_research, {"report": None, "timestamp": None}
    )
    if (
        entry["report"] is None
        or entry["timestamp"] is None
        or datetime.now() - entry["timestamp"] > timedelta(minutes=10)
    ):
        entry.update(
            {
                "report": generate_investment_report.remote(ticker_to_research),
                "timestamp": datetime.now(),
            }
        )
        logging.info(f"Updated report for {ticker_to_research}")

    return entry


@app.local_entrypoint()
def test():
    print(generate_investment_report.remote("SP"))
