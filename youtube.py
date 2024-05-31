from modal import App, Image, web_endpoint

app = App("youtube-video-data")

youtube_image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install youtube_transcript_api"
)


@app.function()
def get_youtube_video_id(url: str) -> str | None:
    """Helper function to get the video ID from a YouTube URL."""
    from urllib.parse import urlparse, parse_qs

    parsed_url = urlparse(url)
    hostname = parsed_url.hostname

    if hostname == "youtu.be":
        return parsed_url.path[1:]
    if hostname in ("www.youtube.com", "youtube.com"):
        if parsed_url.path == "/watch":
            query_params = parse_qs(parsed_url.query)
            return query_params.get("v", [None])[0]
        if parsed_url.path.startswith("/embed/"):
            return parsed_url.path.split("/")[2]
        if parsed_url.path.startswith("/v/"):
            return parsed_url.path.split("/")[2]
    return None


@app.function(image=youtube_image)
@web_endpoint()
def get_youtube_video_captions(url: str) -> str:
    """Use this function to get captions from a YouTube video."""
    from youtube_transcript_api import YouTubeTranscriptApi

    if not url:
        return "No URL provided"

    try:
        video_id = get_youtube_video_id.remote(url)
    except Exception as e:
        return (
            f"Error getting video ID from URL, please provide a valid YouTube url: {e}"
        )

    try:
        captions = YouTubeTranscriptApi.get_transcript(video_id)
        if captions:
            return " ".join(line["text"] for line in captions)
        return "No captions found for video"
    except Exception as e:
        return f"Error getting captions for video: {e}"
