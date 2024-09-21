import os
import logging
from typing import Iterable
from datetime import date, datetime, timedelta

import modal

from utils.options_watchlist import add_to_watchlist

logging.basicConfig(level=logging.INFO)

app = modal.App("volatility-analysis")

tastytrade_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install --upgrade tastytrade fastapi pydantic pytz"]
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


@app.function(
    image=tastytrade_image,
    secrets=[modal.Secret.from_name("tastytrade")],
)
def main(required_tickers: list[str] = ()):
    from decimal import Decimal
    import pytz

    import tastytrade

    # instead of chekcing "watchlist", it should check "volatily_report_data" for cacheing
    try:
        if (
            "volatility_report" in tastytrade_dict
            and datetime.now() - tastytrade_dict["volatility_report_updated_at"]
            < timedelta(minutes=10)
            and all(ticker in tickers_dict["watchlist"] for ticker in required_tickers)
        ):
            logging.info("Found cached volatility report.")
            return tastytrade_dict["volatility_report"]
    except KeyError:
        logging.info(
            "Error finding cached volatility report. Creating new volatility report."
        )

    try:
        session = get_tastytrade_session()
        current_position_symbols = get_current_position_symbols(session)

        # ensure current positions and required tickers are in the watchlist:
        add_to_watchlist(set(current_position_symbols) | set(required_tickers))

        watchlist_metrics = tastytrade.metrics.get_market_metrics(
            session, tickers_dict["watchlist"]
        )

        # Filter and sort metrics
        filtered_metrics = list(
            filter(
                lambda x: iv_rank_filter(x.implied_volatility_index_rank)
                or x.symbol in current_position_symbols
                or (
                    x.symbol in required_tickers
                    and x.implied_volatility_index_rank is not None
                ),
                watchlist_metrics,
            )
        )
        sorted_metrics = sorted(
            filtered_metrics,
            key=lambda x: float(x.implied_volatility_index_rank or 0),
            reverse=True,
        )

        def calculate_last_updated(updated_at: datetime) -> str:
            if updated_at:
                if updated_at.tzinfo is None:
                    metric_time = pytz.UTC.localize(updated_at)
                else:
                    metric_time = updated_at.astimezone(pytz.UTC)

                current_time = datetime.now(pytz.UTC)

                time_difference = current_time - metric_time
                if time_difference < timedelta(days=1):
                    last_updated = f"{time_difference.seconds // 3600}h {(time_difference.seconds % 3600) // 60}m ago"
                else:
                    last_updated = f"{time_difference.days}d ago"
                return last_updated
            else:
                return "N/A"

        def calculate_days_to_earnings(
            metric: tastytrade.metrics.MarketMetricInfo,
        ) -> str:
            days_to_earnings = "N/A"
            if metric.earnings and metric.earnings.expected_report_date:
                if metric.earnings.expected_report_date >= date.today():
                    days_to_earnings = (
                        f"{(metric.earnings.expected_report_date - date.today()).days}"
                    )
            return days_to_earnings

        table_rows = []
        for metric in sorted_metrics:
            row = f"""
            <tr>
                <td>{metric.symbol + '*' if metric.symbol in current_position_symbols else metric.symbol}</td>
                <td>{f"{Decimal(metric.implied_volatility_index_rank) * 100:.1f}%" if metric.implied_volatility_index_rank is not None else "N/A"}</td>
                <td>{f"{Decimal(metric.implied_volatility_percentile) * 100:.1f}%" if metric.implied_volatility_percentile is not None else "N/A"}</td>
                <td>{calculate_last_updated(metric.implied_volatility_updated_at)}</td>
                <td>{f"{Decimal(metric.liquidity_rank) * 100:.1f}%" if metric.liquidity_rank is not None else "N/A"}</td>
                <td>{metric.liquidity_rating if metric.liquidity_rating is not None else "N/A"}</td>
                <td>{metric.lendability if metric.lendability is not None else "N/A"}</td>
                <td>{f"{Decimal(metric.borrow_rate) * 100:.1f}%" if metric.borrow_rate is not None else "N/A"}</td>
                <td>{calculate_days_to_earnings(metric)}</td>
            </tr>
            """
            table_rows.append(row)

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

        header_row = "".join(f"<th>{header}</th>" for header in headers)

        report = f"""
        <table class="volatility-table">
            <thead>
                <tr>{header_row}</tr>
            </thead>
            <tbody>
                {"".join(table_rows)}
            </tbody>
        </table>
        """

        tastytrade_dict["volatility_report"] = report
        tastytrade_dict["volatility_report_updated_at"] = datetime.now()

        return tastytrade_dict["volatility_report"]

    except Exception as e:
        logging.error(f"Error generating volatility report: {e}")
        raise e


@app.function(
    allow_concurrent_inputs=10,
    timeout=60,
)
@modal.asgi_app()
def serve():
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    def generate_html_content(report: str, tickers: str = "") -> str:
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Option Analysis</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #121212; color: #e0e0e0; }}
                h1 {{ color: #ffffff; }}
                form {{ margin-bottom: 20px; }}
                input[type="text"] {{ padding: 5px; width: 200px; background-color: #333; color: #e0e0e0; border: 1px solid #555; }}
                input[type="submit"] {{ padding: 5px 10px; background-color: #4CAF50; color: white; border: none; cursor: pointer; }}
                .table-container {{
                    max-height: 80vh;
                    overflow-y: auto;
                }}
                .volatility-table {{
                    width: 100%;
                    border-collapse: collapse;
                    background-color: #1e1e1e;
                }}
                .volatility-table th, .volatility-table td {{
                    border: 1px solid #333;
                    padding: 8px;
                    text-align: left;
                }}
                .volatility-table tr:nth-child(even) {{
                    background-color: #252525;
                }}
                .volatility-table thead {{
                    position: sticky;
                    top: 0;
                    background-color: #333;
                    color: white;
                }}
                .volatility-table th {{
                    background-color: #333;
                    color: white;
                }}
                .iv-rank-low {{ color: #4CAF50; }}
                .iv-rank-high {{ color: #ff4444; }}
                .iv-rank-very-high {{ color: #ff0000; }}
                .liquidity-rating-low {{ color: #ff4444; }}
                .lendability-locate {{ color: #ff4444; }}
                .borrow-rate-high {{ color: #ff4444; }}
                .borrow-rate-very-high {{ color: #ff0000; }}
            </style>
        </head>
        <body>
            <h1>Option Analysis</h1>
            <form action="/refresh" method="post">
                <input type="text" name="tickers" placeholder="Enter tickers (e.g., QQQ, SPY)" value="{tickers}">
                <input type="submit" value="Refresh Report">
            </form>
            <div class="table-container">
                {report}
            </div>
            <script>
                document.querySelectorAll('.volatility-table td:nth-child(2)').forEach(cell => {{
                    const value = parseFloat(cell.textContent);
                    if (value <= 20) {{
                        cell.classList.add('iv-rank-low');
                    }} else if (value >= 80 && value < 100) {{
                        cell.classList.add('iv-rank-high');
                    }} else if (value >= 100) {{
                        cell.classList.add('iv-rank-very-high');
                    }}
                }});
                
                document.querySelectorAll('.volatility-table td:nth-child(3)').forEach(cell => {{
                    const value = parseFloat(cell.textContent);
                    if (value <= 20) {{
                        cell.classList.add('iv-rank-low');
                    }} else if (value >= 80) {{
                        cell.classList.add('iv-rank-high');
                    }}
                }});
                
                document.querySelectorAll('.volatility-table td:nth-child(6)').forEach(cell => {{
                    if (cell.textContent.trim() === '1') {{
                        cell.classList.add('liquidity-rating-low');
                    }}
                }});
                
                document.querySelectorAll('.volatility-table td:nth-child(7)').forEach(cell => {{
                    if (cell.textContent.trim() === 'Locate Required') {{
                        cell.classList.add('lendability-locate');
                    }}
                }});
                
                document.querySelectorAll('.volatility-table td:nth-child(8)').forEach(cell => {{
                    const value = parseFloat(cell.textContent);
                    if (value >= 100 && value < 1000) {{
                        cell.classList.add('borrow-rate-high');
                    }} else if (value >= 1000) {{
                        cell.classList.add('borrow-rate-very-high');
                    }}
                }});
            </script>
        </body>
        </html>
        """

    @app.get("/", response_class=HTMLResponse)
    async def root():
        report = main.remote()
        return HTMLResponse(content=generate_html_content(report))

    @app.post("/refresh", response_class=HTMLResponse)
    async def refresh(tickers: str = Form(default="")):
        required_tickers = [
            ticker.strip() for ticker in tickers.split(",") if ticker.strip()
        ]
        report = main.remote(required_tickers)
        return HTMLResponse(content=generate_html_content(report, tickers))

    return app
