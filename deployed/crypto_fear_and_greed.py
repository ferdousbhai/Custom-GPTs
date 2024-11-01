from modal import App, Image
import logging

logging.basicConfig(level=logging.INFO)

app = App("crypto-fear-and-greed")


@app.function(image=Image.debian_slim(python_version="3.12").pip_install("httpx"))
def fetch_bitcoin_fear_and_greed():
    import httpx

    url = "https://api.alternative.me/fng/"

    try:
        with httpx.Client() as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()["data"][0]
            score, rating = int(data["value"]), data["value_classification"]
            logging.info(f"Bitcoin Fear and Greed: {score}, {rating}")
            return score, rating
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error occurred: {e}")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return None


@app.local_entrypoint()
def test():
    fetch_bitcoin_fear_and_greed.remote()
