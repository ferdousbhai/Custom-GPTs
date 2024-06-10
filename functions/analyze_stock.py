from modal import App, Image, web_endpoint
from .common import ddgs_news
import logging

logging.basicConfig(level=logging.INFO)

app = App("stock-analysis")

finance_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install httpx yfinance tabulate"
)


@app.function(image=finance_image)
@web_endpoint()
async def generate_investment_report(ticker_to_research: str) -> str:
    """
    Generate an investment report for a given ticker.
    This function generates a report with the following sections:
    - Ticker Info
    - Ticker News
    - Analyst Recommendations
    - Top 20 Upgrades/Downgrades
    The data is pulled from yfinance and ddgs.
    """
    import yfinance as yf

    logging.info(f"Generating report for: {ticker_to_research}")

    # Ticker object
    ticker = yf.Ticker(ticker_to_research)

    # Placeholder for all inputs passed to the assistant
    report = []

    # Get ticker info from yfinance
    if ticker.info:
        report.append("Ticker Info:\n" + str(ticker.info))

    # Get news from ddgs
    ticker_news = ddgs_news.remote(ticker_to_research, ticker.info.get("shortName"))
    logging.info("Fetched news")

    if ticker_news:
        report.append("Ticker News:\n" + str(ticker_news))

    # Get analyst recommendations from yfinance
    if not ticker.recommendations.empty:  # recommendations is a DataFrame
        logging.info("Fetched analyst recommendations")
        report.append("Analyst Recommendations:\n" + ticker.recommendations.to_string())

    # Get upgrades and downgrades from yfinance
    if not ticker.upgrades_downgrades.empty:  # upgrades_downgrades is a DataFrame
        logging.info("Fetched upgrades and downgrades")
        report.append(
            "Upgrades/Downgrades:\n" + ticker.upgrades_downgrades.head(20).to_string()
        )

    final_report = "\n\n".join(report)
    logging.info(f"Generated report for ticker: {ticker_to_research}:\n{final_report}")
    return final_report
