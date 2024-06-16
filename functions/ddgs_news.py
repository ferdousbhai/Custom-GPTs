from modal import App, Image, Secret, Dict

import logging

logging.basicConfig(level=logging.INFO)

app = App("ddgs-news")

embedding_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install openai numpy"
)

ddgs_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install duckduckgo_search"
)

ddgs_news_results = Dict.from_name("ddgs_news_results", create_if_missing=True)


@app.function(image=embedding_image, secrets=[Secret.from_name("openai")])
def filter_relevant_news(
    search_term: str,
    description: str,
    news_items: list[dict],
    similarity_threshold: float = 0.8,
) -> list[dict]:
    """
    Filters news items based on their relevance to a given search term and description.
    """
    import numpy as np
    import openai

    client = openai.OpenAI()

    texts = [f"{search_term}\n{description}"] + [
        f"{item['title']}\n{item['body']}" for item in news_items
    ]

    try:
        response = client.embeddings.create(input=texts, model="text-embedding-ada-002")
        embeddings = [r.embedding for r in response.data]
    except Exception as e:
        logging.error(f"Failed to get embeddings: {e}")
        logging.info("Returning news items without filtering.")
        return news_items

    search_embedding = embeddings[0]
    news_embeddings = embeddings[1:]

    def cosine_similarity(search_embedding, news_embeddings):
        search_embedding = np.array(search_embedding)
        news_embeddings = np.array(news_embeddings)
        dot_product = np.dot(news_embeddings, search_embedding)
        norm_product = np.linalg.norm(search_embedding) * np.linalg.norm(
            news_embeddings, axis=1
        )
        return dot_product / norm_product

    similarities = cosine_similarity(
        np.array(search_embedding), np.array(news_embeddings)
    )
    relevant_indices = np.where(similarities > similarity_threshold)[0]
    relevant_news = [news_items[idx] for idx in relevant_indices]

    return relevant_news


@app.function(image=ddgs_image)
async def get_news_list(
    search_term: str, description: str, max_results: int = 5
) -> list[dict] | None:
    """
    Get the top news for a given search term from DuckDuckGo
    """
    from duckduckgo_search import AsyncDDGS

    async with AsyncDDGS() as client:
        try:
            news_items = await client.anews(
                keywords=f"{search_term} {description}", max_results=max_results
            )
            return [
                {"title": item["title"], "body": item["body"], "url": item["url"]}
                for item in news_items
            ]
        except Exception as e:
            logging.error(f"Failed to get news: {e}")
            return None


@app.function()
async def ddgs_news(
    search_term: str, description: str, max_results: int = 5
) -> list[dict] | None:
    """
    Get the top news for a given search term from DuckDuckGo and filter out the irrelevant ones based on the description
    """
    from time import time
    import re

    # Sanitize the search_term to be used as a dictionary key
    sanitized_search_term = re.sub(r"\W+", "_", search_term.lower().strip())

    # Check if the news is already cached
    result = ddgs_news_results.get(sanitized_search_term)
    if result and time() - result["updated_at"] < 600:
        logging.info(f"Loaded {sanitized_search_term} news from previous run.")
        return result["data"]

    # Fetch from DDGS
    news_list = await get_news_list.remote.aio(search_term, description, max_results)
    if not news_list:
        logging.info(f"No news found for {search_term}")
        return None

    # filter out the irrelevant items
    relevant_news = filter_relevant_news.remote(search_term, description, news_list)

    # save to dict
    ddgs_news_results[sanitized_search_term] = {
        "updated_at": time(),
        "data": relevant_news,
    }
    logging.info(f"Cached {sanitized_search_term} news to dict.")
    return relevant_news
