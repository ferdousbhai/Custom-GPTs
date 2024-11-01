import os
import logging
from modal import App, Cron, Secret

from function_registry import functions
from utils.options_watchlist import add_to_watchlist

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App("cronjobs")


@app.function(
    schedule=Cron("15 0 * * *"),  # 0:15am (UTC)
    secrets=[Secret.lookup("telegram")],
)
def cron_job(send_to_telegram: bool = True):
    output_messages = []

    def add_message(condition, message):
        if condition:
            output_messages.append(message)
        logger.info(message)

    # CNN fear and greed index
    score, rating = functions["fetch_fear_and_greed"].remote()
    add_message(
        score > 75 or score < 25, f"🔔 CNN Fear & Greed Index is {score} - {rating}."
    )

    # Add trending stocks to watchlist
    add_to_watchlist(
        tickers=functions["get_top_trending_tickers"].remote(num_stocks=10)
    )

    # Crypto funding rates
    crypto_tickers = ["BTC", "ETH"]
    funding_rates = functions["get_crypto_funding_rates"].map(crypto_tickers)
    for ticker, rate in zip(crypto_tickers, funding_rates):
        add_message(rate < 0, f"🔔 {ticker}-PERP funding rate is negative: {rate:.4%}.")
        add_message(rate > 0.002, f"🔔 {ticker}-PERP funding rate is high: {rate:.4%}.")

    # Bitcoin fear and greed index
    score, rating = functions["fetch_bitcoin_fear_and_greed"].remote()
    add_message(
        score > 75 or score < 25,
        f"🔔 Bitcoin Fear & Greed Index is {score} - {rating}.",
    )

    # Get crypto IV rank
    crypto_iv_ranks = functions["scrape_crypto_iv_rank"].map(crypto_tickers)
    for ticker, iv_rank in zip(crypto_tickers, crypto_iv_ranks):
        if iv_rank is not None:
            add_message(
                iv_rank < 0.2 or iv_rank > 0.8, f"🔔 {ticker} IV Rank is {iv_rank:.1%}!"
            )
        else:
            logger.warning(f"🔔 {ticker} IV Rank is not available.")

    # Send messages to Telegram
    if send_to_telegram:
        for message in output_messages:
            functions["send_message"].spawn(
                bot_token=os.environ["ASK_DAN_BOT_TOKEN"],
                chat_id=int(os.environ["LONG_VOL_CHANNEL_CHAT_ID"]),
                text=message,
            )

    return output_messages


@app.local_entrypoint()
def test():
    output_messages = cron_job.remote(False)
    for message in output_messages:
        print(message)
