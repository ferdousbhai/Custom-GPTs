import os
import logging

from modal import App, Function, Cron, Secret

from utils.options_watchlist import add_to_watchlist


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App("cronjobs")

# deployed modal functions
send_message = Function.lookup("send-message-to-tg", "send_message")

fetch_fear_and_greed = Function.lookup("fear-and-greed", "fetch_fear_and_greed")
get_top_trending_tickers = Function.lookup(
    "trending-stocks", "get_top_trending_tickers"
)

fetch_bitcoin_fear_and_greed = Function.lookup(
    "crypto-fear-and-greed", "fetch_bitcoin_fear_and_greed"
)
get_crypto_funding_rates = Function.lookup(
    "crypto-funding-rates", "get_crypto_funding_rates"
)
scrape_crypto_iv_rank = Function.lookup("crypto-iv-rank", "scrape_crypto_iv_rank")


@app.function(
    schedule=Cron("15 0 * * *"),  # 0:15am (UTC)
    secrets=[Secret.lookup("telegram")],
)
def cron_job(send_to_telegram: bool = True):
    output_messages: list[str] = []
    # cnn fear and greed index
    score, rating = fetch_fear_and_greed.remote()
    if score > 80 or score < 20:
        output_messages.append(f"🔔 CNN Fear & Greed Index is {score} - {rating}.")
    logger.info(f"🔔 CNN Fear & Greed Index is {score} - {rating}.")

    # add trending stocks to watchlist
    trending_tickers = get_top_trending_tickers.remote(num_stocks=10)
    add_to_watchlist(tickers=trending_tickers)

    # crypto
    crypto_tickers = ["BTC", "ETH"]

    ## get crypto funding rates
    funding_rates = list(get_crypto_funding_rates.map(crypto_tickers))
    for ticker, funding_rate in zip(crypto_tickers, funding_rates):
        logger.info(f"🔔 {ticker}-PERP funding rate is {funding_rate:.4%}.")
        if funding_rate < 0:
            output_messages.append(
                f"🔔 {ticker}-PERP funding rate is negative: {funding_rate:.4%}."
            )
        if funding_rate > 0.002:  # Over 100% annualized
            output_messages.append(
                f"🔔 {ticker}-PERP funding rate is high: {funding_rate:.4%}."
            )

    # bitcoin fear and greed index
    score, rating = fetch_bitcoin_fear_and_greed.remote()
    logger.info(f"🔔 Bitcoin Fear & Greed Index is {score} - {rating}.")
    if score > 80 or score < 20:
        output_messages.append(f"🔔 Bitcoin Fear & Greed Index is {score} - {rating}.")

    ## get crypto iv rank
    iv_ranks = list(scrape_crypto_iv_rank.map(crypto_tickers))
    for ticker, iv_rank in zip(crypto_tickers, iv_ranks):
        if iv_rank is not None:
            logger.info(f"🔔 {ticker} IV Rank is {iv_rank:.1%}.")
            if iv_rank < 0.2 or iv_rank > 0.8:
                output_messages.append(f"🔔 {ticker} IV Rank is {iv_rank:.1%}!")
            else:
                logger.warning(f"🔔 {ticker} IV Rank is not available.")

    # send message to telegram
    if send_to_telegram:
        for message in output_messages:
            send_message.spawn(
                bot_token=os.environ["ASK_DAN_BOT_TOKEN"],
                chat_id=int(os.environ["LONG_VOL_CHANNEL_CHAT_ID"]),
                text=message,
            )

    return output_messages


# test
@app.local_entrypoint()
def test():
    output_messages = cron_job.remote(False)
    for message in output_messages:
        print(message)
