import os
import modal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("IV-rank-report")

send_message = modal.Function.lookup("send-message-to-tg-channel", "send_message")

tastytrade_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install tastytrade tabulate"]
)

tickers_dict = modal.Dict.from_name("tickers", create_if_missing=True)


def get_position_tickers(session, account) -> list[str]:
    from tastytrade.order import InstrumentType

    positions = account.get_positions(session)

    tickers = set()

    for position in positions:
        if position.instrument_type == InstrumentType.EQUITY:
            tickers.add(position.symbol)
        elif position.instrument_type == InstrumentType.EQUITY_OPTION:
            tickers.add(position.underlying_symbol)

    return list(tickers)


def get_report(
    watchlist_metrics: list,
    positions_metrics: list,
    min_iv_rank: float = 0.2,
    max_iv_rank: float = 0.8,
) -> str:
    from decimal import Decimal
    from tabulate import tabulate
    from datetime import date

    # Filter watchlist metrics to keep only items with IV rank > 80% or < 20%
    filtered_watchlist_metrics = [
        metric
        for metric in watchlist_metrics
        if (
            metric.implied_volatility_index_rank is not None
            and (
                float(metric.implied_volatility_index_rank) > max_iv_rank
                or float(metric.implied_volatility_index_rank) < min_iv_rank
            )
        )
    ]
    logging.info(
        f"Filtered watchlist: {[(metric.symbol, metric.implied_volatility_index_rank) for metric in filtered_watchlist_metrics]}"
    )

    # combine and sort by IV rank
    combined_metrics = sorted(
        {
            item.symbol: item for item in positions_metrics + filtered_watchlist_metrics
        }.values(),
        key=lambda x: Decimal(x.implied_volatility_index_rank)
        if x.implied_volatility_index_rank is not None
        else Decimal("-Infinity"),
        reverse=True,
    )

    # Construct table data
    table_data = []
    for metric in combined_metrics:
        symbol = f"{metric.symbol}*" if metric in positions_metrics else metric.symbol
        iv_rank = (
            f"{Decimal(metric.implied_volatility_index_rank) * 100:.1f}%"
            if metric.implied_volatility_index_rank is not None
            else "N/A"
        )
        liquidity = (
            f"{Decimal(metric.liquidity_rank) * 100:.1f}%"
            if metric.liquidity_rank is not None
            else "N/A"
        )
        days_to_earnings = (
            f"{(metric.earnings.expected_report_date - date.today()).days}"
            if metric.earnings and metric.earnings.expected_report_date >= date.today()
            else "N/A"
        )
        table_data.append([symbol, iv_rank, liquidity, days_to_earnings])

    headers = [
        "Symbol",
        "IV Rank",
        "Liquidity",
        "Days to Earnings",
    ]

    return tabulate(table_data, headers=headers, tablefmt="plain")


@app.function(
    image=tastytrade_image,
    secrets=[modal.Secret.from_name("tastytrade"), modal.Secret.from_name("telegram")],
    schedule=modal.Cron("0 9 * * 1-5"),  # 9am (UTC) weekdays
)
def main(post_to_tg: bool = True):
    from tastytrade import ProductionSession, Account, metrics

    session = ProductionSession(
        os.environ["TASTYTRADE_USER"], os.environ["TASTYTRADE_PASSWORD"]
    )

    account = Account.get_accounts(session)[0]  # TODO: handle multiple accounts

    position_tickers = get_position_tickers(session, account)

    watchlist_metrics = metrics.get_market_metrics(session, tickers_dict["watchlist"])
    position_metrics = metrics.get_market_metrics(session, position_tickers)

    report = get_report(watchlist_metrics, position_metrics)
    logging.info(report)

    if post_to_tg:
        send_message.spawn(
            bot_token=os.environ["ASK_DAN_BOT_TOKEN"],
            chat_id=int(os.environ["LONG_VOL_CHANNEL_CHAT_ID"]),
            text=report,
        )

    return report


# testing
@app.local_entrypoint()
def test():
    print(main.remote(post_to_tg=False))
