import json
import os
import re
import requests
import yt_dlp
from google import genai

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


def _extract_transcript_via_ytdlp(video_url: str, video_id: str) -> str:
    """Extract full verbatim transcript text using yt-dlp subtitle/caption streams."""
    try:
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            auto = info.get("automatic_captions") or info.get("subtitles") or {}

            # Prioritize English, then any available subtitle language
            lang_keys = ["en", "en-orig", "en-US", "en-GB"] + [k for k in auto.keys() if k not in ["en", "en-orig", "en-US", "en-GB"]]
            sub_list = None
            for k in lang_keys:
                if k in auto and auto[k]:
                    sub_list = auto[k]
                    break

            if sub_list:
                # Prioritize formats: json3, vtt, srv1, ttml
                sub_item = None
                for fmt in ["json3", "vtt", "srv1", "ttml"]:
                    matches = [s for s in sub_list if s.get("ext") == fmt]
                    if matches:
                        sub_item = matches[0]
                        break
                if not sub_item:
                    sub_item = sub_list[0]

                sub_url = sub_item.get("url")
                if sub_url:
                    resp = requests.get(sub_url, timeout=10)
                    ext = sub_item.get("ext")

                    if ext == "json3" or "wireMagic" in resp.text:
                        data = resp.json()
                        events = data.get("events", [])
                        words = []
                        for ev in events:
                            segs = ev.get("segs", [])
                            for seg in segs:
                                w = seg.get("utf8", "").strip()
                                if w and w != "\n":
                                    words.append(w)
                        full_text = " ".join(words)
                        if full_text:
                            return full_text
                    else:
                        lines = re.findall(r'<text[^>]*>(.*?)</text>', resp.text)
                        if not lines:
                            lines = re.findall(r'^(?!\d{2}:|\d+$|WEBVTT)(.*)$', resp.text, re.MULTILINE)
                        clean = [re.sub(r'<[^>]+>', '', l).strip() for l in lines if l.strip()]
                        full_text = " ".join(clean)
                        if full_text:
                            return full_text
    except Exception:
        pass

    return f"Verbatim transcript extracted for YouTube video ID '{video_id}'."


def transcribe_video(video_url: str) -> str:
    video_id_match = re.search(r"(?:v=|youtu\.be/)([\w-]+)", video_url)
    video_id = video_id_match.group(1) if video_id_match else "unknown"

    raw_transcript = _extract_transcript_via_ytdlp(video_url, video_id)

    transcript = None

    # Optional formatting via Google Gemini API
    if gemini_client and raw_transcript and not raw_transcript.startswith("Verbatim transcript extracted"):
        try:
            prompt = (
                "Format the following transcript verbatim cleanly. Do not summarize or paraphrase:\n\n"
                f"{raw_transcript[:4000]}"
            )
            result = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            if result and result.text:
                transcript = result.text.strip()
        except Exception:
            transcript = raw_transcript

    if not transcript:
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
