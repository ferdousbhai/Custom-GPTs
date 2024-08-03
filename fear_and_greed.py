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

    response = httpx.get(url, headers=headers)
    logging.info(f"Response status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        fear_and_greed = data.get("fear_and_greed", {})
        score, rating = (
            int(fear_and_greed.get("score", {})),
            fear_and_greed.get("rating", {}),
        )
        return (score, rating)
    else:
        logging.error(f"Failed to fetch data: {response.text}")
        return None


# testing
@app.local_entrypoint()
def test():
    fetch_fear_and_greed.remote()
