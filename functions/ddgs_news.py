from modal import App, Image, Secret, web_endpoint

from .common import gpt_data_vol

import logging

logging.basicConfig(level=logging.INFO)

app = App("ddgs-news")

eval_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install openai numpy"
)

ddgs_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install duckduckgo_search"
)


@app.function(image=eval_image, secrets=[Secret.from_name("openai")])
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


@app.function(image=ddgs_image, volumes={"/data": gpt_data_vol})
@web_endpoint()
def ddgs_news(
    search_term: str, description: str, max_results: int = 5
) -> list[dict] | None:
    """
    Get the top news for a given search term from DuckDuckGo and filter out the irrelevant ones based on the description
    """
    import os
    from time import time
    import pickle
    from duckduckgo_search import DDGS

    # check if data already exists and was run in the last 10 minutes
    if os.path.exists(f"/data/{search_term}.pkl"):
        with open(f"/data/{search_term}.pkl", "rb") as f:
            try:
                file_content = pickle.load(f)
                data = file_content.get("data")
                timestamp = file_content.get("timestamp")
                if time() - timestamp < 600:
                    logging.info(f"Loaded from pickle:\n{data}")
                    return data
            except Exception as e:
                logging.error(f"Failed to load data from pickle: {e}")

    # if data doesn't exist or was run in the last 10 minutes, fetch from DDGS
    news_list = DDGS().news(keywords=search_term, max_results=max_results)
    if not news_list:
        return None

    # filter out the irrelevant news items
    relevant_news = filter_relevant_news.remote(search_term, description, news_list)

    # save to volume
    with open(f"/data/{search_term}.pkl", "wb") as f:
        pickle.dump({"timestamp": time(), "data": relevant_news}, f)
    gpt_data_vol.commit()

    logging.info(f"Saved news to volume as {search_term}.pkl")

    return relevant_news


# @app.local_entrypoint()
# def test_ddgs_news():
#     print(ddgs_news.remote("NVDA", "Nvidia company"))
