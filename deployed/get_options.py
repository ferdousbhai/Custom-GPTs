from modal import App, Image, Dict
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging

logging.basicConfig(level=logging.INFO)

app = App("get-options")

image = Image.debian_slim().pip_install("pandas", "yfinance", "tabulate")

options_dict = Dict.from_name("options-data", create_if_missing=True)


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


@app.function(image=image)
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
    str: A string containing the options table.

    Example:
    get_options("AAPL", 20, date(2024, 1, 1), date(2024, 12, 31), Decimal(200))
    """
    import pandas as pd
    import yfinance as yf
    from tabulate import tabulate

    # Simplify caching logic
    if ticker_symbol in options_dict:
        cached_data = options_dict[ticker_symbol]
        if datetime.now() - cached_data["updated_at"] < timedelta(minutes=1):
            logging.info(f"Found cached options for {ticker_symbol}")
            return cached_data["data"]

    try:
        ticker = yf.Ticker(ticker_symbol)
        expiration_dates = ticker.options

        # Simplify date filtering
        if start_date or end_date:
            expiration_dates = [
                exp
                for exp in expiration_dates
                if (
                    not start_date
                    or datetime.strptime(exp, "%Y-%m-%d").date() >= start_date
                )
                and (
                    not end_date
                    or datetime.strptime(exp, "%Y-%m-%d").date() <= end_date
                )
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

        # Simplify price target filtering
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

        result = [
            [
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
            for _, option in top_option_choices.iterrows()
        ]

        headers = [
            "Option Description",
            "Open Interest",
            "Implied Volatility",
            "Volume",
            "Price",
        ]
        table = tabulate(result, headers, tablefmt="plain")

        options_dict[ticker_symbol] = {"data": table, "updated_at": datetime.now()}
        logging.info(table)
        return table

    except Exception as e:
        logging.error(f"Error retrieving options for {ticker_symbol}: {e}")
        return None


# testing
@app.local_entrypoint()
def run():
    get_options.remote("QQQ", 20, date(2025, 1, 1), date(2025, 12, 31), Decimal(600))
