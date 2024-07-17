import os
import modal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("IV-rank-report")

send_message = modal.Function.lookup("send-message-to-tg-channel", "send_message")

tastytrade_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install tastytrade tabulate"]
)

llm_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install openai instructor"]
)

tickers_dict = modal.Dict.from_name("tickers", create_if_missing=True)


def get_position_tickers(session, account) -> list[str]:
    from tastytrade.order import InstrumentType

    positions = account.get_positions(session)

    tickers = set()

    for position in positions:
        logging.info(position)
        if position.instrument_type == InstrumentType.EQUITY:
            tickers.add(position.symbol)
        elif position.instrument_type == InstrumentType.EQUITY_OPTION:
            tickers.add(position.underlying_symbol)

    return list(tickers)


@app.function(
    image=llm_image,
    secrets=[modal.Secret.from_name("openai")],
)
def generate_recommendations(user_message: str, model: str = "gpt-4o") -> str:
    from pydantic import BaseModel, Field
    import instructor
    from openai import OpenAI

    class Response(BaseModel):
        reasoning: str = Field(
            description="Explain your reasoning here, given the guideline. Explain why you're making your recommendation."
        )
        recommendations: str = Field(
            description="Offer recommendations to buy to open, sell to close, or hold positions if you see any interesting opportunities."
        )

    client = instructor.from_openai(OpenAI())
    system_message = (
        "You are a world class investor with high risk tolerance tasked with analyzing options trading metrics and providing recommendations."
        "You will be given a table of metrics for a watchlist of instruments by the user."
        "Review each instrument in the table and comment on any interesting option investing opportunity if you notice any."
        "The symbols with an asterisk (*) next to them represent open option positions. Comment if the user should consider increasing position, holding or closing positions."
        "## Guideline:"
        "- Buy during periods of low volatility, low liquidity. Close positions during periods of high volatility, high liquidity."
        "- IV can also rise in anticipation of events such as earnings (when the company is expected to report earnings) and fall after the event."
        "- Make fewer, better decisions. Your default position is to do nothing. You don't need to make a recommendation if you're unsure."
        "Use markdown formatting for your response."
    )

    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        model=model,
        response_model=Response,
    )
    logging.info(response)

    return response.recommendations


@app.function(
    image=tastytrade_image,
    secrets=[modal.Secret.from_name("tastytrade"), modal.Secret.from_name("telegram")],
    schedule=modal.Cron("0 9 * * 1-5"),  # 9am (UTC) weekdays
)
def main(post_to_tg: bool = True):
    from tastytrade import ProductionSession, Account
    from tastytrade.metrics import get_market_metrics

    session = ProductionSession(
        os.environ["TASTYTRADE_USER"], os.environ["TASTYTRADE_PASSWORD"]
    )

    account = Account.get_accounts(session)[0]  # TODO: handle multiple accounts

    position_tickers = get_position_tickers(session, account)

    watchlist_metrics = get_market_metrics(session, tickers_dict["watchlist"])
    position_metrics = get_market_metrics(session, position_tickers)

    report = get_report(watchlist_metrics, position_metrics)
    logging.info(report)

    ai_response = generate_recommendations.remote(report)
    logging.info(ai_response)

    if post_to_tg:
        for message_text in [report, ai_response]:
            send_message.spawn(
                bot_token=os.environ["ASK_DAN_BOT_TOKEN"],
                chat_id=int(os.environ["LONG_VOL_CHANNEL_CHAT_ID"]),
                text=message_text,
            )

    return f"{report}\n\n{ai_response}"


def get_report(watchlist_metrics, positions_metrics) -> str:
    from decimal import Decimal
    from tabulate import tabulate
    from datetime import date

    # sort watchlist metrics by IV rank in decending order
    sorted_watchlist_metrics = sorted(
        watchlist_metrics,
        key=lambda x: x.implied_volatility_index_rank or Decimal("0"),
        reverse=True,
    )

    # Combine top 10, bottom 10 from watchlist, and all position metrics
    combined_metrics = {
        item.symbol: item
        for item in positions_metrics
        + sorted_watchlist_metrics[:10]
        + sorted_watchlist_metrics[-10:]
    }.values()

    # Remove duplicates and sort again by IV rank
    unique_metrics = sorted(
        {metric.symbol: metric for metric in combined_metrics}.values(),
        key=lambda x: x.implied_volatility_index_rank or Decimal("0"),
        reverse=True,
    )

    # Construct table data
    table_data = []
    for metric in unique_metrics:
        symbol = f"{metric.symbol}*" if metric in positions_metrics else metric.symbol
        iv_rank = f"{Decimal(metric.implied_volatility_index_rank) * 100:.1f}%"
        liquidity = (
            f"{Decimal(metric.liquidity_rank) * 100:.1f}%"
            if metric.liquidity_rank
            else ""
        )
        days_to_earnings = (
            f"{(metric.earnings.expected_report_date - date.today()).days}"
            if metric.earnings and metric.earnings.expected_report_date >= date.today()
            else ""
        )
        table_data.append([symbol, iv_rank, liquidity, days_to_earnings])

    headers = [
        "Symbol",
        "IV Rank",
        "Liquidity",
        "Days to Earnings",
    ]

    return tabulate(table_data, headers=headers, tablefmt="plain")


# testing
@app.local_entrypoint()
def test():
    print(main.remote(post_to_tg=False))
