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
    ...
