import os
import logging
from typing import Iterable
from datetime import date, datetime, timedelta

import modal

from utils.options_watchlist import add_to_watchlist

logging.basicConfig(level=logging.INFO)

app = modal.App("volatility-analysis")

tastytrade_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install --upgrade tastytrade tabulate fastapi pydantic pytz"]
)

tickers_dict = modal.Dict.from_name("tickers-data", create_if_missing=True)

tastytrade_dict = modal.Dict.from_name("tastytrade-data", create_if_missing=True)


def get_tastytrade_session():
    from tastytrade import Session

    try:
        if (
            "session" in tastytrade_dict
            and "session_created_at" in tastytrade_dict
            and datetime.now() - tastytrade_dict["session_created_at"]
            < timedelta(days=1)
        ):
            logging.info("Tastytrade session is still valid.")
            return tastytrade_dict["session"]
    except KeyError:
        logging.info("Creating new tastytrade session.")

    try:
        tastytrade_dict["session"] = Session(
            os.environ["TASTYTRADE_USER"], os.environ["TASTYTRADE_PASSWORD"]
        )
        tastytrade_dict["session_created_at"] = datetime.now()
        logging.info("Created new tastytrade session.")
    except KeyError:
        raise ValueError(
            "TASTYTRADE_USER and/or TASTYTRADE_PASSWORD environment variables are not set."
        )

    return tastytrade_dict["session"]


def get_current_position_symbols(session) -> Iterable[str]:
    from tastytrade import Account
    from tastytrade.utils import TastytradeError

    try:
        account = Account.get_account(session, os.getenv("TASTYTRADE_ACCOUNT"))
    except TastytradeError:
        account = Account.get_accounts(session)[0]

    current_positions = account.get_positions(session)

    return {
        current_position.underlying_symbol for current_position in current_positions
    }


def iv_rank_filter(
    iv_rank: str | None, min_iv_rank: float = 0.2, max_iv_rank: float = 0.8
) -> bool:
    if iv_rank is None:
        return False
    try:
        rank = float(iv_rank)
        return rank < min_iv_rank or rank > max_iv_rank
    except ValueError:
        return False


def get_volatility_report(
    watchlist_metrics: list, required_tickers: Iterable[str]
) -> str:
    from decimal import Decimal
    from tabulate import tabulate
    import pytz

    # Filter and sort metrics
    filtered_metrics = filter(
        lambda x: iv_rank_filter(x.implied_volatility_index_rank)
        or x.symbol in required_tickers,
        watchlist_metrics,
    )
    sorted_metrics = sorted(
        filtered_metrics,
        key=lambda x: float(x.implied_volatility_index_rank)
        if x.implied_volatility_index_rank
        else 0,
        reverse=True,
    )

    # Construct table data
    table_data = []
    for metric in sorted_metrics:
        symbol = (
            f"{metric.symbol}*" if metric.symbol in required_tickers else metric.symbol
        )
        iv_rank = (
            f"{Decimal(metric.implied_volatility_index_rank) * 100:.1f}%"
            if metric.implied_volatility_index_rank is not None
            else "N/A"
        )
        implied_volatility_percentile = (
            f"{Decimal(metric.implied_volatility_percentile) * 100:.1f}%"
            if metric.implied_volatility_percentile is not None
            else "N/A"
        )
        last_updated = "N/A"
        if metric.implied_volatility_updated_at:
            # Convert the metric's datetime to UTC if it's not already
            if metric.implied_volatility_updated_at.tzinfo is None:
                metric_time = pytz.UTC.localize(metric.implied_volatility_updated_at)
            else:
                metric_time = metric.implied_volatility_updated_at.astimezone(pytz.UTC)

            # Get current time in UTC
            current_time = datetime.now(pytz.UTC)

            time_difference = current_time - metric_time
            if time_difference < timedelta(days=1):
                last_updated = f"{time_difference.seconds // 3600}h {(time_difference.seconds % 3600) // 60}m ago"
            else:
                last_updated = f"{time_difference.days}d ago"
        liquidity_rank = (
            f"{Decimal(metric.liquidity_rank) * 100:.1f}%"
            if metric.liquidity_rank is not None
            else "N/A"
        )
        liquidity_rating = (
            metric.liquidity_rating if metric.liquidity_rating is not None else "N/A"
        )
        lendability = metric.lendability if metric.lendability is not None else "N/A"
        borrow_rate = (
            f"{Decimal(metric.borrow_rate) * 100:.1f}%"
            if metric.borrow_rate is not None
            else "N/A"
        )
        days_to_earnings = "N/A"
        if metric.earnings and metric.earnings.expected_report_date:
            if metric.earnings.expected_report_date >= date.today():
                days_to_earnings = (
                    f"{(metric.earnings.expected_report_date - date.today()).days}"
                )
        table_data.append(
            [
                symbol,
                iv_rank,
                implied_volatility_percentile,
                last_updated,
                liquidity_rank,
                liquidity_rating,
                lendability,
                borrow_rate,
                days_to_earnings,
            ]
        )

    headers = [
        "Symbol",
        "IV Rank",
        "IV Percentile",
        "Last Updated",
        "Liquidity Rank",
        "Liquidity Rating",
        "Lendability",
        "Borrow Rate",
        "Days to Earnings",
    ]

    return tabulate(table_data, headers=headers, tablefmt="github")


@app.function(
    image=tastytrade_image,
    secrets=[
        modal.Secret.from_name("tastytrade"),
        modal.Secret.from_name("auth-token"),
    ],
    keep_warm=1,
)
def main():
    import tastytrade

    try:
        if "volatility_report" in tastytrade_dict and datetime.now() - tastytrade_dict[
            "volatility_report_updated_at"
        ] < timedelta(minutes=10):
            logging.info("Found cached volatility report.")
            return tastytrade_dict["volatility_report"]
    except KeyError:
        logging.info("Creating new volatility report.")

    try:
        session = get_tastytrade_session()
        current_position_symbols = get_current_position_symbols(session)

        # ensure current positions are in the watchlist:
        add_to_watchlist(current_position_symbols)

        watchlist_metrics = tastytrade.metrics.get_market_metrics(
            session, tickers_dict["watchlist"]
        )

        tastytrade_dict["volatility_report"] = get_volatility_report(
            watchlist_metrics, current_position_symbols
        )
        tastytrade_dict["volatility_report_updated_at"] = datetime.now()
    except Exception as e:
        logging.error(f"Error generating volatility report: {e}")
        raise e

    return tastytrade_dict["volatility_report"]


@app.function(
    keep_warm=1,
    allow_concurrent_inputs=10,
    timeout=60,
)
@modal.asgi_app()
def serve():
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def root():
        report = main.remote()
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Option Analysis</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                h1 {{ color: #333; }}
                pre {{ background-color: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <h1>Option Analysis</h1>
            <pre>{report}</pre>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    return app


@app.local_entrypoint()
def test():
    print(main.remote())
