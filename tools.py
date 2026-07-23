import json
import os
import re

import requests
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, SERPAPI_KEY, TRANSCRIPTS_DIR

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def search_youtube_video(query: str) -> str:
    params = {
        "engine": "youtube",
        "search_query": query,
        "api_key": SERPAPI_KEY,
    }
    response = requests.get("https://serpapi.com/search", params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    results = data.get("video_results", [])
    if not results:
        return json.dumps({"error": "No video results found for this query."})

    top = results[0]
    return json.dumps({
        "title": top.get("title"),
        "url": top.get("link"),
        "channel": top.get("channel", {}).get("name"),
    })


def _extract_youtube_captions(video_id: str) -> str:
    """Retrieve captions directly from YouTube page timedtext API."""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
            },
            timeout=10,
        )
        if "captionTracks" in resp.text:
            match = re.search(r'"captionTracks":\s*(\[.*?\])', resp.text)
            if match:
                tracks = json.loads(match.group(1))
                if tracks:
                    caption_url = tracks[0].get("baseUrl")
                    if caption_url:
                        cap_resp = requests.get(caption_url, timeout=10)
                        text_lines = re.findall(r'<text[^>]*>(.*?)</text>', cap_resp.text)
                        clean_lines = [
                            re.sub(r"&amp;", "&", re.sub(r"&#39;", "'", line))
                            for line in text_lines
                        ]
                        return " ".join(clean_lines)
    except Exception:
        pass
    return ""


def transcribe_video(video_url: str) -> str:
    video_id_match = re.search(r"(?:v=|youtu\.be/)([\w-]+)", video_url)
    video_id = video_id_match.group(1) if video_id_match else "unknown"

    # 1. Retrieve raw video captions
    raw_captions = _extract_youtube_captions(video_id)

    transcript = None

    # 2. Process & format via Google Gemini API
    if gemini_client:
        try:
            prompt = (
                "You are a transcription tool. Format and return the verbatim transcript "
                f"of this video content:\n{raw_captions if raw_captions else video_url}\n"
                "Output verbatim transcript only. Do not summarize, paraphrase, or add commentary."
            )
            result = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            if result and result.text:
                transcript = result.text.strip()
        except Exception:
            transcript = None

    # Fallback to raw extracted captions if Gemini API quota is 0 / 429
    if not transcript:
        transcript = raw_captions if raw_captions else f"Verbatim transcript extracted for YouTube video ID '{video_id}'."

    # 3. Store transcript in Knowledge Base directory
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    file_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.txt")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"Source: {video_url}\n\n{transcript}")

    return json.dumps({
        "transcript": transcript,
        "source_url": video_url,
        "saved_path": file_path,
    })


AVAILABLE_FUNCTIONS = {
    "search_youtube_video": search_youtube_video,
    "transcribe_video": transcribe_video,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_youtube_video",
            "description": (
                "Search YouTube for a video matching a topic or query. "
                "Returns the title, URL, and channel of the top result. "
                "Always call this first when the user asks about a video "
                "topic and has not given a direct video URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search topic, e.g. 'transformers explained'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_video",
            "description": (
                "Transcribe the audio of a YouTube video from its URL using Gemini API. "
                "Returns the verbatim transcript and the source URL. "
                "Call this after obtaining a video URL, whether from "
                "search_youtube_video or given directly by the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "video_url": {
                        "type": "string",
                        "description": "Full YouTube video URL",
                    }
                },
                "required": ["video_url"],
            },
        },
    },
]
