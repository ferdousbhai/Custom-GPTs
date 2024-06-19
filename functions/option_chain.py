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
def get_options(
    ticker_symbol: str, sort_by: str = "openInterest", num_options: int = 12
) -> list[dict]:
    import pandas as pd
    import yfinance as yf

    try:
        ticker = yf.Ticker(ticker_symbol)
        expiration_dates = ticker.options

        all_options_df = pd.DataFrame()

        for expiration in expiration_dates:
            options = ticker.option_chain(expiration)
            puts_and_calls = pd.concat([options.calls, options.puts])
            all_options_df = pd.concat([all_options_df, puts_and_calls])

        logging.info(f"All options:\n{all_options_df}")
        sorted_options = all_options_df.sort_values(by=sort_by, ascending=False)
        top_options = sorted_options.head(num_options).to_dict("records")

        recommended_options = []
        for option in top_options:
            ticker, strike_price, option_type, expiry_date = parse_option_symbol(
                option["contractSymbol"]
            )
            recommended_options.append(
                {
                    "optionDescription": f"{ticker} {strike_price}{option_type} {expiry_date.strftime("%-m/%-d/%y")}",
                    "price": option["ask"] + option["bid"] / 2,
                    "open_interest": option["openInterest"],
                    "volume": option["volume"],
                }
            )

        return recommended_options

    except Exception as e:
        logging.error(f"Error getting options: {e}")
        return []
