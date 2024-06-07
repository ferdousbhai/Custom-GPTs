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
async def assert_relevant(search_term: str, description: str, news_item: dict) -> bool:
    """
    Assert if a news item is relevant
    """
    import numpy as np
    import openai

    client = openai.OpenAI()

    def get_embedding(text: str, model="text-embedding-ada-002") -> list[float]:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding

    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    # find cosine similarity between the prompt and the news item
    search_item = f"{search_term}\n{description}"
    news_item = f"{news_item['title']}\n{news_item['body']}"

    search_embedding = get_embedding(search_item)
    news_embedding = get_embedding(news_item)

    similarity = cosine_similarity(search_embedding, news_embedding)

    return similarity > 0.8


@app.function(image=ddgs_image, volumes={"/data": gpt_data_vol})
@web_endpoint()
async def ddgs_news(
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
    news_list = await DDGS().news(keywords=search_term, max_results=max_results)
    if not news_list:
        return None

    # evaluate if the news items are relevant
    relevances = [
        assert_relevant.remote(search_term, description, news_item)
        for news_item in news_list
    ]

    # filter out the irrelevant news items
    relevant_news = [item for item, relevant in zip(news_list, relevances) if relevant]
    if not relevant_news:
        return None

    # save to volume
    with open(f"/data/{search_term}.pkl", "wb") as f:
        pickle.dump({"timestamp": time(), "data": relevant_news}, f)
    gpt_data_vol.commit()

    logging.info(f"Saved news to volume as {search_term}.pkl")

    return relevant_news
