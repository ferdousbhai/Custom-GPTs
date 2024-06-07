from modal import Volume

import logging

logging.basicConfig(level=logging.INFO)

gpt_data_vol = Volume.from_name("gpt-data-storage")


async def get_news(search_term: str, description: str) -> list[dict] | None:
    import httpx

    try:
        response = httpx.get(
            "https://ai-clone-company--ddgs-news-ddgs-news.modal.run",
            timeout=httpx.Timeout(
                10, read=30
            ),  # 10 seconds connect timeout, 30 seconds read timeout
            params={"search_term": search_term, "description": description},
        )
        return response.json()
    except httpx.ReadTimeout:
        logging.error(
            "The request timed out while trying to read data from the server."
        )
