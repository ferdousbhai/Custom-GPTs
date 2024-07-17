from modal import App, Image
from datetime import date, datetime
from decimal import Decimal
import logging

logging.basicConfig(level=logging.INFO)

app = App("get-options")


image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install pandas yfinance tabulate"
)


def parse_option_symbol(symbol: str):
    """Parse the option symbol to extract the ticker name, date, type (c or p), and strike price"""
    import re

    match = re.match(r"(\w+)\s*(\d{6})([CP])(\d+)", symbol)
    if match is None:
        logging.error(f"Symbol format is incorrect: {symbol}")
        raise ValueError(f"Symbol format is incorrect: {symbol}")
    ticker, date_str, option_type, strike_str = match.groups()
    expiry_date: date = datetime.strptime(date_str, "%y%m%d").date()
    strike_price: Decimal = (
        Decimal(strike_str) / 1000
    )  # the strike price is encoded as an integer representing the price in thousandths of the currency unit.
    return (ticker, strike_price, option_type, expiry_date)


@app.function(image=image, keep_warm=1)
def get_options(
    ticker_symbol: str,
    num_options: int = 10,
    start_date: date | None = None,
    end_date: date | None = None,
    price_target: Decimal | None = None,
) -> str | None:
    """
    Retrieve a list of options with the highest open interest for a given ticker symbol relevant to a forecast, i.e. expiration date is between start_date and end_date, and in the money based on price_target.

    Parameters:
    ticker_symbol (str): The ticker symbol of the stock for which to retrieve options.
    num_options (int, optional): The number of top options to retrieve based on open interest.
    start_date (date, optional): The start date to filter options by expiration date.
    end_date (date, optional): The end date to filter options by expiration date.
    price_target (Decimal, optional): The target price to filter options by strike price.

    Returns:
    str | None: A string containing the options table. Returns None if an error occurs.

    Example:
    get_options("AAPL", 20, date(2024, 1, 1), date(2024, 12, 31), Decimal(200))
    """
    import pandas as pd
    import yfinance as yf
    from tabulate import tabulate

    try:
        ticker = yf.Ticker(ticker_symbol)

        expiration_dates = ticker.options  # list of expiration dates
        if start_date:
            expiration_dates = [
                expiration_date
                for expiration_date in expiration_dates
                if datetime.strptime(expiration_date, "%Y-%m-%d").date() >= start_date
            ]
        if end_date:
            expiration_dates = [
                expiration_date
                for expiration_date in expiration_dates
                if datetime.strptime(expiration_date, "%Y-%m-%d").date() <= end_date
            ]

        options_df = pd.concat(
            [
                pd.concat(
                    [ticker.option_chain(exp).calls, ticker.option_chain(exp).puts]
                )
                for exp in expiration_dates
            ],
            ignore_index=True,
        )

        options_df[["ticker", "strike", "option_type", "expiry"]] = options_df[
            "contractSymbol"
        ].apply(lambda x: pd.Series(parse_option_symbol(x)))

        options_df["price"] = (options_df["ask"] + options_df["bid"]) / 2

        if price_target:
            options_df = options_df[
                (
                    (options_df["option_type"] == "C")
                    & (options_df["strike"] <= price_target)
                )
                | (
                    (options_df["option_type"] == "P")
                    & (options_df["strike"] >= price_target)
                )
            ]

        top_option_choices = options_df.nlargest(num_options, "openInterest")

        result = []
        for _, option in top_option_choices.iterrows():
            option_data = [
                f"{option['ticker']} {option['strike']}{option['option_type']} {option['expiry'].strftime('%-m/%-d/%y')}",
                option["openInterest"],
                f"{round(option['impliedVolatility'] * 100, 2)}%"
                if option.get("impliedVolatility", 0) > 0
                else None,
                option["volume"] if option.get("volume", 0) > 0 else None,
                round(option["price"], 2)
                if option.get("ask", 0) > 0 and option.get("bid", 0) > 0
                else None,
            ]
            result.append(option_data)

            headers = [
                "Option Description",
                "Open Interest",
                "Implied Volatility",
                "Volume",
                "Price",
            ]
            table = tabulate(result, headers, tablefmt="plain")
        logging.info(table)
        return table

    except Exception as e:
        logging.error(f"Error getting options: {e}")
        return None


# testing
@app.local_entrypoint()
def run():
    get_options.remote("QQQ", 20, date(2025, 1, 1), date(2025, 12, 31), Decimal(600))
