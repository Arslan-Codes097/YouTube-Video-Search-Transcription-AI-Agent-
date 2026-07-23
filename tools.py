import json
import os
import re
import requests
from config import SERPAPI_KEY, TRANSCRIPTS_DIR


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


def _extract_transcript_via_api(video_id: str) -> str:
    """Extract full verbatim transcript text using SerpApi."""
    try:
        params = {
            "engine": "youtube_video_transcript",
            "v": video_id,
            "api_key": SERPAPI_KEY,
        }
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            return f"Error extracting transcript: {data['error']}"
            
        transcript_parts = data.get("transcript", [])
        if not transcript_parts:
            return "Error extracting transcript: No transcript available"
            
        full_text = " ".join([item.get("snippet", "").replace('\xa0', ' ').replace('\n', ' ') for item in transcript_parts])
        
        if full_text:
            return full_text
            
    except Exception as e:
        return f"Error extracting transcript: {str(e)}"

    return f"Verbatim transcript extracted for YouTube video ID '{video_id}'."


def transcribe_video(video_url: str) -> str:
    video_id_match = re.search(r"(?:v=|youtu\.be/)([\w-]+)", video_url)
    video_id = video_id_match.group(1) if video_id_match else "unknown"

    raw_transcript = _extract_transcript_via_api(video_id)
    transcript = raw_transcript

    # Store transcript in Knowledge Base directory
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
                "Transcribe the audio of a YouTube video from its URL. "
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
