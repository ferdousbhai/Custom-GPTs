from modal import App, Image
import logging

logging.basicConfig(level=logging.INFO)

app = App("fear-and-greed")


@app.function(image=Image.debian_slim(python_version="3.12").pip_install("httpx"))
def fetch_fear_and_greed():
    import httpx

    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

    # mimic a browser to avoid bot detection
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
        "Origin": "https://www.cnn.com",
    }

    try:
        with httpx.Client() as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        fear_and_greed = data.get("fear_and_greed", {})
        score = int(fear_and_greed.get("score", 0))
        rating = fear_and_greed.get("rating")
        logging.info(f"Fear and Greed score: {score}, rating: {rating}")
        return score, rating
    except (httpx.HTTPStatusError, ValueError, KeyError) as e:
        logging.error(f"Error fetching data: {e}")
        return None


@app.local_entrypoint()
def test():
    fetch_fear_and_greed.remote()
