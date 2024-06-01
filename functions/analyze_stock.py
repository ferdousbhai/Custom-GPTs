from modal import App, Image, web_endpoint

app = App("stock-analysis")

image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install yfinance duckduckgo_search tabulate"
)


@app.function(image=image)
@web_endpoint()
async def generate_investment_report(ticker_to_research: str) -> str:
    """
    Generate an investment report for a given ticker.
    This function generates a report with the following sections:
    - Ticker Info
    - Ticker News
    - Analyst Recommendations
    - Upgrades/Downgrades
    The data is pulled from yfinance and ddgs.
    """
    import yfinance as yf
    from duckduckgo_search import DDGS

    # Ticker object
    ticker = yf.Ticker(ticker_to_research)

    # Placeholder for all inputs passed to the assistant
    report_input = ""

    # Get ticker info from yfinance
    if ticker.info:
        ticker_info_cleaned = {
            "Name": ticker.info.get("shortName"),
            "Symbol": ticker.info.get("symbol"),
            "Current Stock Price": f"{ticker.info.get('regularMarketPrice', ticker.info.get('currentPrice'))} {ticker.info.get('currency', 'USD')}",
            "Market Cap": f"{ticker.info.get('marketCap', ticker.info.get('enterpriseValue'))} {ticker.info.get('currency', 'USD')}",
            "Sector": ticker.info.get("sector"),
            "Industry": ticker.info.get("industry"),
            "EPS": ticker.info.get("trailingEps"),
            "P/E Ratio": ticker.info.get("trailingPE"),
            "52 Week Low": ticker.info.get("fiftyTwoWeekLow"),
            "52 Week High": ticker.info.get("fiftyTwoWeekHigh"),
            "50 Day Average": ticker.info.get("fiftyDayAverage"),
            "200 Day Average": ticker.info.get("twoHundredDayAverage"),
            "Website": ticker.info.get("website"),
            "Summary": ticker.info.get("longBusinessSummary"),
            "Analyst Recommendation": ticker.info.get("recommendationKey"),
            "Number Of Analyst Opinions": ticker.info.get("numberOfAnalystOpinions"),
            "Employees": ticker.info.get("fullTimeEmployees"),
            "Total Cash": ticker.info.get("totalCash"),
            "Free Cash flow": ticker.info.get("freeCashflow"),
            "Operating Cash flow": ticker.info.get("operatingCashflow"),
            "EBITDA": ticker.info.get("ebitda"),
            "Revenue Growth": ticker.info.get("revenueGrowth"),
            "Gross Margins": ticker.info.get("grossMargins"),
            "Ebitda Margins": ticker.info.get("ebitdaMargins"),
        }
        ticker_info_md = "## ticker Info\n\n"
        for key, value in ticker_info_cleaned.items():
            if value:
                ticker_info_md += f"  - {key}: {value}\n\n"
        report_input += "This section contains information about the ticker.\n\n"
        report_input += ticker_info_md
        report_input += "---\n"

    # Get news from ddgs
    ddgs = DDGS()
    ticker_news = ddgs.news(keywords=ticker_to_research, max_results=5)
    if len(ticker_news) > 0:
        ticker_news_md = "## ticker News\n\n\n"
        for news_item in ticker_news:
            ticker_news_md += f"#### {news_item['title']}\n\n"
            if "date" in news_item:
                ticker_news_md += f"  - Date: {news_item['date']}\n\n"
            if "url" in news_item:
                ticker_news_md += f"  - Link: {news_item['url']}\n\n"
            if "source" in news_item:
                ticker_news_md += f"  - Source: {news_item['source']}\n\n"
            if "body" in news_item:
                ticker_news_md += f"{news_item['body']}"
            ticker_news_md += "\n\n"
        report_input += (
            "This section contains the most recent news articles about the ticker.\n\n"
        )
        report_input += ticker_news_md
        report_input += "---\n"

    # Get analyst recommendations from yfinance
    analyst_recommendations = ticker.recommendations
    if not analyst_recommendations.empty:
        report_input += "## Analyst Recommendations\n\n"
        report_input += "This table outlines the most recent analyst recommendations for the stock.\n\n"
        report_input += f"{analyst_recommendations.to_markdown()}\n"
    report_input += "---\n"

    # Get upgrades and downgrades from yfinance
    upgrades_downgrades = ticker.upgrades_downgrades[0:20]
    if not upgrades_downgrades.empty:
        upgrades_downgrades_md = upgrades_downgrades.to_markdown()
        report_input += "## Upgrades/Downgrades\n\n"
        report_input += "This table outlines the most recent upgrades and downgrades for the stock.\n\n"
        report_input += f"{upgrades_downgrades_md}\n"
    report_input += "---\n"

    return f"Here's a report about: {ticker_to_research}\n\n\n{report_input}"
