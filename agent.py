import json

from groq import Groq

from config import DEFAULT_MODEL, GROQ_API_KEY
from tools import AVAILABLE_FUNCTIONS, TOOL_SCHEMAS

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = (
    "You are a video research agent. You have two tools: "
    "search_youtube_video and transcribe_video. "
    "If the user gives a topic (not a URL), call search_youtube_video first. "
    "If the user gives a direct YouTube URL, skip search and call "
    "transcribe_video directly with that URL."
)


def _execute_tool_call(tool_call):
    function_name = tool_call.function.name
    function_args = json.loads(tool_call.function.arguments)
    function_to_call = AVAILABLE_FUNCTIONS[function_name]
    return function_name, function_to_call(**function_args)


def run_agent(user_query: str, model: str = DEFAULT_MODEL, progress_callback=None) -> dict:
    trace = []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]

    has_url = "youtube.com" in user_query or "youtu.be" in user_query
    first_forced_tool = "transcribe_video" if has_url else "search_youtube_video"

    if progress_callback:
        if has_url:
            progress_callback("transcribe_video", "started", {"video_url": user_query})
        else:
            progress_callback("search_youtube_video", "started", {"query": user_query})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOL_SCHEMAS,
        tool_choice={"type": "function", "function": {"name": first_forced_tool}},
    )

    message = response.choices[0].message
    messages.append(message)

    video_url = None

    for tool_call in message.tool_calls:
        name, result = _execute_tool_call(tool_call)
        parsed_result = json.loads(result)
        trace.append({"tool": name, "arguments": tool_call.function.arguments, "result": result})
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": name,
            "content": result,
        })
        if name == "search_youtube_video":
            video_url = parsed_result.get("url")
            if progress_callback:
                progress_callback("search_youtube_video", "completed", parsed_result)
        elif name == "transcribe_video" and progress_callback:
            progress_callback("transcribe_video", "completed", parsed_result)

    if first_forced_tool == "search_youtube_video":
        if video_url is None:
            return {
                "transcript": None,
                "source_url": None,
                "answer": "No video found for that query.",
                "trace": trace,
            }

        if progress_callback:
            progress_callback("transcribe_video", "started", {"video_url": video_url})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice={"type": "function", "function": {"name": "transcribe_video"}},
        )
        message = response.choices[0].message
        messages.append(message)

        for tool_call in message.tool_calls:
            name, result = _execute_tool_call(tool_call)
            parsed_result = json.loads(result)
            trace.append({"tool": name, "arguments": tool_call.function.arguments, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": result,
            })
            if progress_callback:
                progress_callback("transcribe_video", "completed", parsed_result)

    transcription_result = json.loads(trace[-1]["result"])
    transcript = transcription_result.get("transcript")
    source_url = transcription_result.get("source_url")

    answer = f"{transcript}\n\nSource: {source_url}"

    return {
        "transcript": transcript,
        "source_url": source_url,
        "answer": answer,
        "trace": trace,
    }
