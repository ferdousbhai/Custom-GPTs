from modal import App, Image, Dict

import logging

logging.basicConfig(level=logging.INFO)

app = App("ddgs-news")

ddgs_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install duckduckgo_search"
)

ddgs_news_results = Dict.from_name("ddgs_news_results", create_if_missing=True)


@app.function(image=ddgs_image, keep_warm=1)
async def get_ddgs_news(
    search_term: str,
    search_description: str | None = None,
    max_results: int = 6,
    cache_ttl: int = 600,
) -> list[str] | None:
    """
    Get the top news for a given search term from DuckDuckGo
    """
    from time import time
    import re
    from duckduckgo_search import AsyncDDGS

    # Sanitize the search_term to be used as a dictionary key
    sanitized_search_term = re.sub(r"\W+", "_", search_term.lower().strip())

    # Check if the news is already cached
    result = ddgs_news_results.get(sanitized_search_term)
    if result and time() - result["updated_at"] < cache_ttl:
        logging.info(f"Loaded {sanitized_search_term} news from previous run.")
        return result["data"]

    # Fetch from DDGS
    try:
        news_items = await AsyncDDGS().anews(
            keywords=f"{search_term} {search_description}", max_results=max_results
        )
        news_list = [
            f"**{item['title']}**\n\n{item['body']}\n\n[Source: {item['source']}]({item['url']})"
            for item in news_items
        ]
    except Exception as e:
        logging.error(f"Failed to get news: {e}")
        return None

    if not news_list:
        logging.info(f"No news found for {search_term}")
        return None

    # save to dict
    ddgs_news_results[sanitized_search_term] = {
        "updated_at": time(),
        "data": news_list,
    }
    logging.info(f"Cached {sanitized_search_term} news to dict.")

    return news_list


# testing
@app.local_entrypoint()
async def test():
    result = await get_ddgs_news.remote.aio("NVDA", "NVIDIA")
    print(result)
