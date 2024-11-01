import inspect
from typing import get_type_hints

from modal import Function

functions: dict[str, Function] = {
    "send_message": Function.lookup("send-message-to-tg", "send_message"),
    "fetch_fear_and_greed": Function.lookup("fear-and-greed", "fetch_fear_and_greed"),
    "fetch_bitcoin_fear_and_greed": Function.lookup(
        "crypto-fear-and-greed", "fetch_bitcoin_fear_and_greed"
    ),
    "get_crypto_funding_rates": Function.lookup(
        "crypto-funding-rates", "get_crypto_funding_rates"
    ),
    "scrape_crypto_iv_rank": Function.lookup("crypto-iv-rank", "scrape_crypto_iv_rank"),
    "get_ddgs_news": Function.lookup("ddgs-news", "get_ddgs_news"),
    "get_options": Function.lookup("get-options", "get_options"),
    "get_stock_analysis": Function.lookup(
        "stock-analysis", "generate_investment_report"
    ),
    "get_top_trending_tickers": Function.lookup(
        "trending-stocks", "get_top_trending_tickers"
    ),
    "get_volatility_report": Function.lookup("volatility-analysis", "generate_report"),
}


f: Function = functions["get_volatility_report"]
print(f.get_raw_f())


def create_openai_schema(func):
    wrapped = func.__wrapped__  # Get the original function
    signature = inspect.signature(wrapped)
    docstring = inspect.getdoc(wrapped) or ""
    type_hints = get_type_hints(wrapped)

    parameters = {}
    for name, param in signature.parameters.items():
        param_type = type_hints.get(name, inspect.Parameter.empty)
        param_schema = {"type": str(param_type.__name__)}
        if param.default != inspect.Parameter.empty:
            param_schema["default"] = param.default
        parameters[name] = param_schema

    schema = {
        "name": wrapped.__name__,
        "description": docstring,
        "parameters": {"type": "object", "properties": parameters},
    }

    return schema


function_schemas = {}


def get_function_schema(function_name: str):
    return function_schemas.get(function_name, {})
