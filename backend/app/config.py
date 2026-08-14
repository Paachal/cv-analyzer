"""
Centralized configuration loaded from environment variables (.env file).
Never hardcode secrets here — this module only reads them.
"""
import os
from dotenv import load_dotenv

# Load variables from a .env file in the backend/ directory if present.
load_dotenv()


class Settings:
    # --- Gemini ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))

    # --- MongoDB ---
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "cv_analyzer")

    # --- Uploads / validation ---
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
    MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {".pdf", ".docx"}
    MIN_EXTRACTED_TEXT_CHARS: int = int(os.getenv("MIN_EXTRACTED_TEXT_CHARS", "200"))

    # --- CORS ---
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # --- App ---
    APP_NAME: str = "CV Analyzer"
    API_PREFIX: str = "/api"


settings = Settings()


def validate_settings() -> list:
    """Return a list of human-readable warnings about missing critical config.
    Called at startup so the app fails loudly (in logs) rather than silently
    misbehaving when someone forgets to set the API key."""
    warnings = []
    if not settings.GEMINI_API_KEY:
        warnings.append(
            "GEMINI_API_KEY is not set. Set it in backend/.env — "
            "analysis requests will fail until you do."
        )
    return warnings
