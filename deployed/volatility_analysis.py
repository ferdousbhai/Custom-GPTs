import os
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel
import modal

from utils.options_watchlist import add_to_watchlist

logging.basicConfig(level=logging.INFO)

app = modal.App("volatility-analysis")

tastytrade_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install --upgrade tastytrade fastapi pydantic pytz"]
)

tickers_dict = modal.Dict.from_name("tickers-data", create_if_missing=True)

tastytrade_dict = modal.Dict.from_name("tastytrade-data", create_if_missing=True)


class MetricData(BaseModel):
    """
    Represents processed market metric data for a single symbol.
    """

    symbol: str
    has_position: bool
    iv_rank: str = "N/A"
    iv_percentile: str = "N/A"
    last_updated: str = "N/A"
    liquidity_rank: str = "N/A"
    liquidity_rating: str = "N/A"
    lendability: str = "N/A"
    borrow_rate: str = "N/A"
    days_to_earnings: str = "N/A"

    class Config:
        frozen = True


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


def get_current_position_symbols(session) -> set[str]:
    from tastytrade import Account
    from tastytrade.utils import TastytradeError

    try:
        account = Account.get_account(session, os.getenv("TASTYTRADE_ACCOUNT"))
    except TastytradeError:
        accounts = Account.get_accounts(session)
        if not accounts:
            raise ValueError("No accounts found for the given session.")
        account = accounts[0]

    current_positions = account.get_positions(session)

    # return the set of underlying symbols
    return {position.underlying_symbol for position in current_positions}


def get_volatility_data(required_tickers: list[str] = ()) -> list[MetricData]:
    """
    Fetches and processes volatility metrics for watchlist symbols.

    Args:
        required_tickers: List of ticker symbols to include regardless of metrics

    Returns:
        List of processed metric data for each relevant symbol
    """
    import pytz
    import tastytrade

    try:
        if (
            "volatility_data" in tastytrade_dict
            and datetime.now() - tastytrade_dict["volatility_data_updated_at"]
            < timedelta(minutes=10)
            and all(
                any(
                    data.symbol == ticker for data in tastytrade_dict["volatility_data"]
                )
                for ticker in required_tickers
            )
        ):
            logging.info("Found cached volatility data.")
            return tastytrade_dict["volatility_data"]
    except KeyError:
        logging.info("Creating new volatility data.")

    session = get_tastytrade_session()
    current_position_symbols = get_current_position_symbols(session)

    # ensure current positions and required tickers are in the watchlist:
    add_to_watchlist(set(current_position_symbols) | set(required_tickers))

    watchlist_metrics = tastytrade.metrics.get_market_metrics(
        session, tickers_dict["watchlist"]
    )

    # Filter and sort metrics
    filtered_metrics = [
        x
        for x in watchlist_metrics
        if (
            x.implied_volatility_index_rank is not None
            and float(x.implied_volatility_index_rank) < 0.2
            and x.implied_volatility_updated_at is not None
        )  # cheap
        or x.symbol in current_position_symbols  # open position
        or x.symbol in required_tickers  # required by user
    ]
    sorted_metrics = sorted(
        filtered_metrics,
        key=lambda x: float(x.implied_volatility_index_rank or 0),
        reverse=True,
    )

    def calculate_last_updated(updated_at: datetime) -> str:
        if not updated_at:
            return "N/A"
        metric_time = (
            updated_at.replace(tzinfo=pytz.UTC)
            if updated_at.tzinfo is None
            else updated_at.astimezone(pytz.UTC)
        )
        time_difference = datetime.now(pytz.UTC) - metric_time
        return (
            f"{time_difference.days}d ago"
            if time_difference.days
            else f"{time_difference.seconds // 3600}h {(time_difference.seconds % 3600) // 60}m ago"
        )

    def calculate_days_to_earnings(metric: tastytrade.metrics.MarketMetricInfo) -> str:
        if metric.earnings and metric.earnings.expected_report_date:
            if metric.earnings.expected_report_date >= date.today():
                return str((metric.earnings.expected_report_date - date.today()).days)
        return "N/A"

    processed_data = []
    for metric in sorted_metrics:
        data = MetricData(
            symbol=metric.symbol,
            has_position=metric.symbol in current_position_symbols,
            iv_rank=f"{Decimal(metric.implied_volatility_index_rank) * 100:.1f}%"
            if metric.implied_volatility_index_rank is not None
            else "N/A",
            iv_percentile=f"{Decimal(metric.implied_volatility_percentile) * 100:.1f}%"
            if metric.implied_volatility_percentile is not None
            else "N/A",
            last_updated=calculate_last_updated(metric.implied_volatility_updated_at),
            liquidity_rank=f"{Decimal(metric.liquidity_rank) * 100:.1f}%"
            if metric.liquidity_rank is not None
            else "N/A",
            liquidity_rating=str(metric.liquidity_rating)
            if metric.liquidity_rating is not None
            else "N/A",
            lendability=str(metric.lendability)
            if metric.lendability is not None
            else "N/A",
            borrow_rate=f"{Decimal(metric.borrow_rate) * 100:.1f}%"
            if metric.borrow_rate is not None
            else "N/A",
            days_to_earnings=calculate_days_to_earnings(metric),
        )
        processed_data.append(data)

    tastytrade_dict["volatility_data"] = processed_data
    tastytrade_dict["volatility_data_updated_at"] = datetime.now()

    return processed_data


@app.function(
    image=tastytrade_image,
    secrets=[modal.Secret.from_name("tastytrade")],
)
def generate_report(required_tickers: list[str] = (), tickers_input: str = "") -> str:
    """
    Generates a complete HTML report of volatility metrics.

    Args:
        required_tickers: List of ticker symbols to include in the report
        tickers_input: Original comma-separated ticker input string for form value

    Returns:
        Complete HTML string containing the formatted report page
    """
    try:
        processed_data = get_volatility_data(required_tickers)

        # Generate table rows
        table_rows = []
        for data in processed_data:
            row = f"""
            <tr>
                <td>{data.symbol + '*' if data.has_position else data.symbol}</td>
                <td>{data.iv_rank}</td>
                <td>{data.iv_percentile}</td>
                <td>{data.last_updated}</td>
                <td>{data.liquidity_rank}</td>
                <td>{data.liquidity_rating}</td>
                <td>{data.lendability}</td>
                <td>{data.borrow_rate}</td>
                <td>{data.days_to_earnings}</td>
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

        report_table = f"""
        <table class="volatility-table">
            <thead>
                <tr>{header_row}</tr>
            </thead>
            <tbody>
                {"".join(table_rows)}
            </tbody>
        </table>
        """

        # Generate complete HTML page
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
                <input type="text" name="tickers" placeholder="Enter tickers (e.g., QQQ, SPY)" value="{tickers_input}">
                <input type="submit" value="Refresh Report">
            </form>
            <div class="table-container">
                {report_table}
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

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse(content=generate_report.remote())

    @app.post("/refresh", response_class=HTMLResponse)
    async def refresh(tickers: str = Form(default="")):
        required_tickers = [
            ticker.strip() for ticker in tickers.split(",") if ticker.strip()
        ]
        return HTMLResponse(content=generate_report.remote(required_tickers, tickers))

    return app
