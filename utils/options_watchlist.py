from modal import Dict
import logging

logging.basicConfig(level=logging.INFO)

tickers_dict = Dict.from_name("tickers", create_if_missing=True)


def add_to_watchlist(tickers: list[str]):
    watchlist: list[str] = tickers_dict["watchlist"]
    for ticker in tickers:
        if ticker not in watchlist:
            watchlist.append(ticker)
            logging.info(f"Added {ticker} to watchlist.")
        else:
            logging.info(f"{ticker} is already in the watchlist.")
    tickers_dict["watchlist"] = watchlist
    logging.info(f"Updated watchlist: {watchlist}")


def remove_from_watchlist(tickers: list[str]):
    watchlist: list[str] = tickers_dict["watchlist"]
    for ticker in tickers:
        if ticker in watchlist:
            watchlist.remove(ticker)
            logging.info(f"Removed {ticker} from watchlist.")
        else:
            logging.info(f"{ticker} is not in the watchlist.")
    tickers_dict["watchlist"] = watchlist
    logging.info(f"Updated watchlist: {watchlist}")


if __name__ == "__main__":
    # add_to_watchlist(tickers=["TSM"])
