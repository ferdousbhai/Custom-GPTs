import logging
from typing import Iterable

from modal import Dict


logging.basicConfig(level=logging.INFO)

tickers_dict = Dict.from_name("tickers-data", create_if_missing=True)


def add_to_watchlist(tickers: Iterable[str]):
    try:
        watchlist: list[str] = tickers_dict["watchlist"]
    except KeyError:
        watchlist = []
    for ticker in tickers:
        if ticker not in watchlist:
            watchlist.append(ticker)
            logging.info(f"Adding {ticker} to watchlist.")
    tickers_dict["watchlist"] = watchlist
    logging.info(f"Updated watchlist: {watchlist}")


def remove_from_watchlist(tickers: Iterable[str]):
    try:
        watchlist: list[str] = tickers_dict["watchlist"]
    except KeyError:
        watchlist = []
    for ticker in tickers:
        if ticker in watchlist:
            watchlist.remove(ticker)
            logging.info(f"Removing {ticker} from watchlist.")
    tickers_dict["watchlist"] = watchlist
    logging.info(f"Updated watchlist: {watchlist}")


if __name__ == "__main__":
    add_to_watchlist(
        tickers=[
            "NVDA",
            "MSFT",
            "AAPL",
            "GOOGL",
            "AMZN",
            "TSLA",
            "META",
            "PLTR",
            "GME",
            "CHWY",
            "COIN",
            "AMD",
            "TQQQ",
            "QQQ",
            "SMH",
            "VIX",
            "TLT",
            "TSM",
            "SQ",
            "DELL",
            "SMCI",
            "BABA",
            "DJT",
            "ARM",
            "MSTR",
            "ASML",
            "RIVN",
            "AVGO",
            "MRVL",
            "SPY",
            "DIS",
            "GOOG",
            "CRWD",
            "AM",
            "DTE",
            "IBM",
            "CMG",
            "IWM",
            "OS",
            "ASTS",
            "NKE",
            "DM",
            "CRM",
            "ME",
            "VC",
            "MCD",
            "MU",
            "BIDU",
            "IT",
            "NFLX",
            "TLRY",
            "FXI",
            "SBUX",
            "PYPL",
            "CVNA",
            "INTC",
            "ALL",
            "VOO",
            "SP",
        ]
    )
