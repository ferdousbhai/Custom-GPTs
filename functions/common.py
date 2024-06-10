import modal

gpt_data_vol = modal.Volume.from_name("gpt-data")

ddgs_news = modal.Function.lookup("ddgs-news", "ddgs_news")
