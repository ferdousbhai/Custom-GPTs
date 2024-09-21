from modal import App, Image, Dict

import logging

logging.basicConfig(level=logging.INFO)

app = App("ddgs-news")

ddgs_news_results = Dict.from_name("ddgs_news_results", create_if_missing=True)


@app.function(
    image=Image.debian_slim(python_version="3.12").pip_install("duckduckgo_search")
)
async def get_ddgs_news(
    search_term: str,
    search_description: str | None = None,
    max_results: int = 6,
    cache_ttl: int = 600,
) -> list[str] | None:
    """Get the top news for a given search term from DuckDuckGo"""
    from time import time
    import re
    from duckduckgo_search import AsyncDDGS

    sanitized_search_term = re.sub(r"\W+", "_", search_term.lower().strip())
    result = ddgs_news_results.get(sanitized_search_term)

    if result and time() - result["updated_at"] < cache_ttl:
        logging.info(f"Loaded {sanitized_search_term} news from previous run.")
        return result["data"]

    try:
        news_items = await AsyncDDGS().anews(
            keywords=f"{search_term} {search_description}".strip(),
            max_results=max_results,
        )
        news_list = [
            f"**{item['title']}**\n\n{item['body']}\n\n[Source: {item['source']}]({item['url']})"
            for item in news_items
        ]
        if not news_list:
            logging.info(f"No news found for {search_term}")
            return None

        ddgs_news_results[sanitized_search_term] = {
            "updated_at": time(),
            "data": news_list,
        }
        logging.info(f"Cached {sanitized_search_term} news to dict.")
        return news_list
    except Exception as e:
        logging.error(f"Failed to get news: {e}")
        return None


# testing
@app.local_entrypoint()
async def test():
    result = await get_ddgs_news.remote.aio("NVDA", "NVIDIA")
    print(result)
