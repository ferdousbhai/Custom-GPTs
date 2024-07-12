from modal import App, Image
import logging

logging.basicConfig(level=logging.INFO)

app = App("get-options")


yfinance_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install pandas yfinance"
)


def parse_option_symbol(symbol: str):
    """Parse the option symbol to extract the ticker name, date, type (c or p), and strike price"""
    import re
    import datetime
    from decimal import Decimal
    from typing import Literal

    match = re.match(r"(\w+)\s*(\d{6})([CP])(\d+)", symbol)
    if match is None:
        raise ValueError(f"Symbol format is incorrect: {symbol}")
    ticker, date_str, option_type, strike_str = match.groups()
    expiry_date: datetime.date = datetime.datetime.strptime(date_str, "%y%m%d").date()
    strike_price: Decimal = Decimal(strike_str) / 1000
    option_type: Literal["c", "p"] = "c" if option_type == "C" else "p"

    return (ticker, strike_price, option_type, expiry_date)


@app.function(image=yfinance_image)
def get_options(ticker_symbol: str, num_options: int = 6) -> list[dict]:
    """Get the options with the highest open interest for a given ticker symbol."""
    import pandas as pd
    import yfinance as yf

    try:
        ticker = yf.Ticker(ticker_symbol)
        expiration_dates = ticker.options
        all_options_df = pd.concat(
            [
                pd.concat(
                    [
                        ticker.option_chain(expiration).calls,
                        ticker.option_chain(expiration).puts,
                    ]
                )
                for expiration in expiration_dates
            ],
            ignore_index=True,
        )
        all_options_df["price"] = (all_options_df["ask"] + all_options_df["bid"]) / 2

        top_options = (
            all_options_df.sort_values(by=["openInterest"], ascending=False)
            .head(num_options)
            .to_dict("records")
        )
        logging.info(f"Top options:\n{top_options}")

        result = []
        for option in top_options:
            ticker, strike_price, option_type, expiry_date = parse_option_symbol(
                option["contractSymbol"]
            )
            option_data = {
                "optionDescription": f"{ticker} {strike_price}{option_type} {expiry_date.strftime('%-m/%-d/%y')}",
                "openInterest": option["openInterest"],
            }
            if option.get("ask", 0) > 0 and option.get("bid", 0) > 0:
                option_data["price"] = round(option["price"], 2)
            if option.get("impliedVolatility", 0) > 0:
                option_data["impliedVolatility"] = (
                    f"{round(option['impliedVolatility'] * 100, 2)}%"
                )
            if option.get("volume", 0) > 0:
                option_data["volume"] = option["volume"]
            result.append(option_data)
        return result

    except Exception as e:
        logging.error(f"Error getting options: {e}")
        return []
