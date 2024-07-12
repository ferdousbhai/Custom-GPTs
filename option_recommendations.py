import os
import modal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("option-recommendations")

send_message = modal.Function.lookup("send-message-to-tg-channel", "send_message")

tastytrade_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install tastytrade tabulate"]
)

llm_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install openai instructor"]
)

tickers_dict = modal.Dict.from_name("tickers", create_if_missing=True)


@app.function(
    image=tastytrade_image,
    secrets=[modal.Secret.from_name("tastytrade")],
    schedule=modal.Period(days=1),
)
def tastytrade_app():
    from tastytrade import ProductionSession
    from tastytrade.metrics import get_market_metrics

    session = ProductionSession(
        os.environ["TASTYTRADE_USER"], os.environ["TASTYTRADE_PASSWORD"]
    )

    watchlist_tickers = tickers_dict["watchlist"]
    position_tickers = get_position_tickers(session)
    tickers_dict["positions"] = position_tickers

    watchlist_metrics = get_market_metrics(session, watchlist_tickers)
    position_metrics = get_market_metrics(session, position_tickers)

    formatted_data = format_metrics(watchlist_metrics, position_metrics)

    if should_notify(watchlist_metrics, position_metrics):
        logging.info("Sending report to TG channel.")
        send_message.remote(formatted_data)
        logging.info("Generating AI response.")
        ai_response = generate_recommendations.remote(formatted_data)
        logging.info("Sending AI response to TG channel.")
        send_message.remote(ai_response)

    return f"{formatted_data}\n\n{ai_response}"


def format_metrics(watchlist, positions) -> str:
    from decimal import Decimal
    from tabulate import tabulate
    from datetime import date

    combined_metrics = positions.copy()  # initialize with positions
    for item in watchlist:
        if item not in positions:
            combined_metrics.append(item)

    logging.info(f"Found {len(combined_metrics)} instruments.")

    sorted_metrics = sorted(
        combined_metrics,
        key=lambda x: x.implied_volatility_index_rank or Decimal("0"),
        reverse=True,
    )

    table_data = [
        [
            f"{metric.symbol}*" if metric in positions else metric.symbol,
            f"{Decimal(metric.implied_volatility_index_rank) * 100:.1f}%",
            f"{Decimal(metric.liquidity_rank) * 100:.1f}%"
            if metric.liquidity_rank
            else "",
            f"{(metric.earnings.expected_report_date - date.today()).days}"
            if metric.earnings and metric.earnings.expected_report_date >= date.today()
            else "",
        ]
        for metric in sorted_metrics
    ]

    headers = [
        "Symbol",
        "IV Rank",
        "Liquidity",
        "Days to Earnings",
    ]

    formatted_data = tabulate(table_data, headers=headers, tablefmt="plain")
    logging.info(formatted_data)

    return formatted_data


def should_notify(watchlist, positions):
    return any(
        float(metric.implied_volatility_index_rank) < 0.2 for metric in watchlist
    ) or any(float(metric.implied_volatility_index_rank) > 0.75 for metric in positions)


def get_position_tickers(session) -> list[str]:
    from tastytrade import Account
    from tastytrade.order import InstrumentType

    account = Account.get_accounts(session)[0]
    positions = account.get_positions(session)

    logging.info(f"Found {len(positions)} positions.")

    tickers = set()

    for position in positions:
        logging.info(position)
        if position.instrument_type == InstrumentType.EQUITY:
            tickers.add(position.symbol)
        elif position.instrument_type == InstrumentType.EQUITY_OPTION:
            tickers.add(position.underlying_symbol)

    return list(tickers)


# TODO: actions should be a list of actions to take, which will be handled by a separate function
@app.function(
    image=llm_image,
    secrets=[modal.Secret.from_name("openai")],
)
def generate_recommendations(user_message: str, model: str = "gpt-4o") -> str:
    from pydantic import BaseModel, Field
    import instructor
    from openai import OpenAI
    from datetime import datetime

    class Response(BaseModel):
        reasoning: str = Field(
            description="Explain your reasoning here, considering the IV Rank, Liquidity, and the given guideline. Explain why you're making your recommendation."
        )
        recommendations: str = Field(
            description="Offer recommendations to buy to open, sell to close, or hold positions if you see any interesting opportunities."
        )

    client = instructor.from_openai(OpenAI())
    system_message = (
        "You are a world class investor with high risk tolerance tasked with analyzing options trading metrics and providing recommendations."
        "You will be given a table of metrics for a watchlist of instruments by the user."
        "Comment on any interesting option investing opportunities if you notice any."
        "The symbols with an asterisk (*) next to them represent open option positions. Comment if the user should consider increasing position, holding or closing positions."
        "Your general guideline is the following:"
        "- Buy during periods of low volatility, low liquidity. Close positions during periods of high volatility, high liquidity."
        "- IV can also rise in anticipation of earnings (when the company is expected to report earnings) and fall after the event."
        "- Make fewer, better decisions. Your default position is to do nothing. You don't need to make a recommendation if you're unsure."
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
    tickers_dict["recommendations"] = response.recommendations
    tickers_dict["last_updated"] = datetime.now()
    return response.recommendations


@app.local_entrypoint()
def main():
    print(tastytrade_app.remote())
