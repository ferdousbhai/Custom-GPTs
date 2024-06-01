from modal import App, Image, web_endpoint

from models import Story

import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

app = App("trending-stocks")

ddgs_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install duckduckgo_search"
)

httpx_image = Image.debian_slim(python_version="3.12").run_commands("pip install httpx")


@app.function(image=httpx_image)
async def get_top_trending_stonks(num_stocks: int) -> list[str] | None:
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


@app.function(image=ddgs_image)
async def ddgs_news(keywords: str, max_results: int = 5) -> list[Story] | None:
    """
    Get the top news for a given ticker symbol from DuckDuckGo
    """
    from duckduckgo_search import DDGS

    ddgs = DDGS()
    ticker_news = ddgs.news(keywords=keywords, max_results=max_results)
    if not ticker_news:
        return None
    ticker_stories = []
    for news_item in ticker_news:
        ticker_stories.append(
            Story(
                title=news_item["title"],
                url=news_item["url"],
                timestamp=news_item["date"],
                summary=news_item["body"],
            )
        )

    return ticker_stories


@app.function()
@web_endpoint()
def get_trending_stocks_and_news(num_stocks: int = 6) -> list[tuple[str, list[Story]]]:
    """
    Get the top trending stocks from ApeWisdom and the top news for each ticker from DuckDuckGo
    """
    list_of_ticker_stories: list[tuple[str, list[Story]]] = []

    tickers: list[str] | None = get_top_trending_stonks.remote(num_stocks)
    if tickers is None:
        return []
    for ticker in tickers:
        ticker_stories: list[Story] = ddgs_news.remote(ticker) or []
        list_of_ticker_stories.append((ticker, ticker_stories))

    return list_of_ticker_stories
