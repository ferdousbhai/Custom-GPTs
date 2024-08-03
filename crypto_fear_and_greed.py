from modal import App, Image
import logging

logging.basicConfig(level=logging.INFO)

app = App("crypto-fear-and-greed")


@app.function(image=Image.debian_slim(python_version="3.12").pip_install("httpx"))
def fetch_bitcoin_fear_and_greed():
    import httpx

    url = "https://api.alternative.me/fng/"

    response = httpx.get(url)
    logging.info(f"Response status: {response.status_code}")

    if response.status_code == 200:
        response = response.json()
        data = response.get("data", {})
        score, rating = int(data[0]["value"]), data[0]["value_classification"]
        logging.info(f"Bitcoin Fear and Greed: {score}, {rating}")
        return (score, rating)
    else:
        logging.error(f"Failed to fetch data: {response.text}")
        return None


# testing
@app.local_entrypoint()
def test():
    fetch_bitcoin_fear_and_greed.remote()
