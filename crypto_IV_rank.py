import os
import modal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("crypto_IV_rank")

playwright_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    "apt-get update",
    "apt-get install -y software-properties-common",
    "apt-add-repository non-free",
    "apt-add-repository contrib",
    "pip install playwright",
    "playwright install-deps chromium",
    "playwright install chromium",
)

send_message = modal.Function.lookup("send-message-to-tg-channel", "send_message")


@app.function(image=playwright_image, secrets=[modal.Secret.from_name("telegram")])
def scrape_crypto_iv_rank(
    ticker: str, min_iv_rank: float = 0.2, max_iv_rank: float = 0.8
) -> float | None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(f"https://www.deribit.com/statistics/{ticker}/volatility-index")

            # Extract the IV Rank value based on the sibling relationship
            page.wait_for_selector("xpath=//span[contains(., 'IV Rank')]")
            iv_rank_element = page.query_selector(
                "xpath=//span[contains(., 'IV Rank')]/following-sibling::h4"
            )

            if iv_rank_element:
                iv_rank_str = iv_rank_element.inner_text()
                iv_rank = float(iv_rank_str) / 100
                logging.info(f"{ticker} IV Rank: {iv_rank:.1%}")
                if iv_rank == 0:
                    logging.error(
                        f"{ticker} IV Rank is 0! The website structure might have changed."
                    )
                    return None
                elif iv_rank < min_iv_rank or iv_rank > max_iv_rank:
                    send_message.spawn(
                        bot_token=os.environ["ASK_DAN_BOT_TOKEN"],
                        chat_id=int(os.environ["LONG_VOL_CHANNEL_CHAT_ID"]),
                        text=f"{ticker} IV Rank is {iv_rank:.1%}!",
                    )
                return iv_rank
            else:
                logging.info(
                    "IV Rank not found. The website structure might have changed."
                )
                return None

        except Exception as e:
            print(f"An error occurred: {e}")
            return None

        finally:
            browser.close()


@app.function(schedule=modal.Cron("0 9 * * *"))  # 9am (UTC)
def main():
    list(scrape_crypto_iv_rank.map(["BTC", "ETH"]))


# testing
@app.local_entrypoint()
def test():
    scrape_crypto_iv_rank.remote("BTC")
    scrape_crypto_iv_rank.remote("ETH")
