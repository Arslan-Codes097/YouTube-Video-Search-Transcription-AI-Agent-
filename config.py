import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

DEFAULT_MODEL = "llama-3.3-70b-versatile"

ALLOWED_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
]

TRANSCRIPTS_DIR = "transcripts"
