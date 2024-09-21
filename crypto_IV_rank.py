import modal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("crypto-iv-rank")

image = modal.Image.debian_slim(python_version="3.12").run_commands(
    "apt-get update",
    "apt-get install -y software-properties-common",
    "apt-add-repository non-free",
    "apt-add-repository contrib",
    "pip install playwright",
    "playwright install-deps chromium",
    "playwright install chromium",
)


@app.function(image=image)
def scrape_crypto_iv_rank(ticker: str) -> float | None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(f"https://www.deribit.com/statistics/{ticker}/volatility-index")
            page.wait_for_selector("xpath=//span[contains(., 'IV Rank')]")
            iv_rank_element = page.query_selector(
                "xpath=//span[contains(., 'IV Rank')]/following-sibling::h4"
            )

            if not iv_rank_element:
                logging.info(
                    "IV Rank not found. The website structure might have changed."
                )
                return None

            iv_rank = (
                float(iv_rank_element.inner_text().split(":")[-1].strip().rstrip("%"))
                / 100
            )
            logging.info(f"{ticker} IV Rank: {iv_rank:.1%}")

            if iv_rank == 0:
                logging.error(
                    f"{ticker} IV Rank is 0! The website structure might have changed."
                )
                return None

            return iv_rank

        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return None

        finally:
            browser.close()


@app.local_entrypoint()
def test():
    scrape_crypto_iv_rank.remote("BTC")
    scrape_crypto_iv_rank.remote("ETH")
