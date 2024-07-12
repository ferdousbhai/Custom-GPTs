import os
import modal
from decimal import Decimal
from datetime import date
from typing import Literal
import logging

logging.basicConfig(level=logging.INFO)

app = modal.App("tastytrade-agent")

tastytrade_image = modal.Image.debian_slim().pip_install("tastytrade")

llm_image = modal.Image.debian_slim(python_version="3.12").run_commands(
    ["pip install openai instructor"]
)

tickers_dict = modal.Dict.from_name("tickers")
# tickers_dict["recommendations"] contains the tickers to trade
# tickers_dict["last_updated"] contains the last time the recommendations were updated


@app.function(secrets=[modal.Secret.from_name("tastytrade")], image=tastytrade_image)
def get_session():
    from tastytrade import ProductionSession

    return ProductionSession(
        os.getenv("TASTYTRADE_USER"),
        os.getenv("TASTYTRADE_PASSWORD"),
    )


@app.function(image=tastytrade_image)
async def is_market_open(session) -> bool:
    """
    Check if the market is open using DXLinkStreamer.
    """
    from tastytrade import DXLinkStreamer
    from tastytrade.dxfeed import EventType

    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(
            EventType.PROFILE, ["SPY"]
        )  # Subscribe to a common symbol
        profile = await streamer.get_event(EventType.PROFILE)
        return profile.tradingStatus == "Open"

# TODO: Should I be using the endpoint in get_options.py instead?
@app.function(image=tastytrade_image)
def get_option(
    session,
    ticker_symbol: str,
    start_expiration: date,
    end_expiration: date,
    price_target: Decimal,
):
    """
    Get a list of possible options to purchase from for a given ticker.
    """
    from tastytrade.instruments import get_option_chain

    chain = get_option_chain(session, ticker_symbol)
    filtered_chain = []
    for exp, options in chain.items():
        if start_expiration <= exp <= end_expiration:
            for option in options:
                if option.strike >= price_target:
                    filtered_chain.append(option)

    # TODO: Sort the filtered_chain by volume and liquidity, discard the ones higher/lower than price_target depending on call or put, return the most liquid; log everything

    return filtered_chain


def get_option_streamer_symbol(
    ticker: str, strike: Decimal, expiry: date, option_type: Literal["C", "P"]
) -> str:
    """
    Get the streamer symbol for an option.
    """
    expiry_str = expiry.strftime("%y%m%d")
    strike_str = f"{strike:f}".rstrip("0").rstrip(".")
    return f".{ticker.upper()}{expiry_str}{option_type}{strike_str}"


@app.function(image=tastytrade_image)
async def get_midprice(session, streamer_symbol: str) -> Decimal:
    """
    Get the mid-price of bid and ask.

    Args:
        session: The active session object.
        streamer_symbol (str): The symbol in DxFeed format.

    Returns:
        Decimal: The mid-price of the bid and ask.
    """
    from tastytrade import DXLinkStreamer
    from tastytrade.dxfeed import EventType

    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(EventType.QUOTE, [streamer_symbol])
        quote = await streamer.get_event(EventType.QUOTE, streamer_symbol)
        mid_price = (quote.bidPrice + quote.askPrice) / 2
        return Decimal(mid_price)


@app.function(image=tastytrade_image)
def buy_to_open_position(session, account, option, amount: Decimal, side: str):
    from tastytrade.order import (
        NewOrder,
        OrderTimeInForce,
        OrderType,
        OrderAction,
        PriceEffect,
    )

    bid_ask_mid_price = get_midprice.remote(session, option.streamer_symbol)
    buy_quantity = amount // bid_ask_mid_price // option.multiplier
    leg = option.build_leg(buy_quantity, OrderAction.BUY_TO_OPEN)

    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=[leg],
        price=bid_ask_mid_price,
        price_effect=PriceEffect.DEBIT,
    )
    response = account.place_order(session, order, dry_run=True)  # a test order
    print(response)


@app.function(image=tastytrade_image)
def sell_to_close_position(session, account, option, amount: Decimal, side: str): ...


@app.function(
    image=llm_image,
    secrets=[modal.Secret.from_name("openai")],
)
def call_agent

@app.local_entrypoint()
def main():
    from tastytrade import Account
    from tastytrade.instruments import Option
    from tastytrade.order import InstrumentType
    from datetime import datetime, timedelta
    import locale

    locale.setlocale(locale.LC_ALL, "en_US.UTF-8")

    session = get_session.remote()
    account = Account.get_accounts(session)[0]
    balances = account.get_balances(session)
    positions = account.get_positions(session)

    cash_available, portfolio_value = (
        balances.derivative_buying_power,
        balances.net_liquidating_value,
    )

    option_positions = []
    for position in positions:
        if position.instrument_type == InstrumentType.EQUITY_OPTION:
            option_positions.append(
                {
                    "streamer_symbol": Option.occ_to_streamer_symbol(position.symbol),
                    "quantity": position.quantity,
                }
            )

    print(f"Cash available: {locale.currency(cash_available, 'USD')}")
    print(f"Portfolio value: {locale.currency(portfolio_value, 'USD')}")
    print(f"Found {len(option_positions)} option positions.")
    for position in option_positions:
        print(f"{str(position['quantity'])} {position['streamer_symbol']}")

    if not is_market_open.remote(session):
        logging.info("Market is not open, exiting.")
        return

    logging.info("Market is open, getting options to trade.")
    recommendations = tickers_dict["recommendations"]
    if tickers_dict["last_updated"] < datetime.now() - timedelta(days=1):
        logging.info("Recommendations are outdated, updating.")
        ...

    # TODO: Call LLM
