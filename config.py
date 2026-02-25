import os
from dotenv import load_dotenv

load_dotenv()

# --- Onyx settings ---
ONYX_BASE_URL = os.getenv("ONYX_BASE_URL", "https://cloud.onyx.app").rstrip("/")
ONYX_AUTH_COOKIE = os.getenv("ONYX_AUTH_COOKIE", "")
ONYX_PERSONA_ID = int(os.getenv("ONYX_PERSONA_ID", "0"))
ONYX_ORIGIN = os.getenv("ONYX_ORIGIN", "webapp")
ONYX_REFERER = os.getenv("ONYX_REFERER", "https://cloud.onyx.app/app")

# --- Server settings ---
API_KEY = os.getenv("API_KEY", "")  # Empty = no auth required
PORT = int(os.getenv("PORT", "8896"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))

# --- Model mapping: external name -> (provider, version) ---
MODEL_MAP = {
    "claude-opus-4.6": ("Anthropic", "claude-opus-4-6"),
    "claude-opus-4.5": ("Anthropic", "claude-opus-4-5"),
    "claude-sonnet-4.5": ("Anthropic", "claude-sonnet-4-5"),
    "gpt-5.2": ("OpenAI", "gpt-5.2"),
    "gpt-5-mini": ("OpenAI", "gpt-5-mini"),
    "gpt-4.1": ("OpenAI", "gpt-4.1"),
    "gpt-4o": ("OpenAI", "gpt-4o"),
    "o3": ("OpenAI", "o3"),
}
