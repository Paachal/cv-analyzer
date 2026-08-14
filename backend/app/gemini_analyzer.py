"""
Gemini analysis engine.

Builds the structured prompt, calls the Gemini API with
response_mime_type="application/json" for strict JSON output, validates
the response against our Pydantic contract, and retries once on
transient failures (rate limits, safety blocks, malformed JSON).

Knows nothing about FastAPI or Mongo — pure "text in, AnalysisResult out".
"""
import json
import logging
import time
from typing import Optional

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from pydantic import ValidationError

from app.config import settings
from app.models import AnalysisResult

logger = logging.getLogger("cv_analyzer.gemini")

_configured = False


class GeminiAnalysisError(Exception):
    """Raised when analysis could not be produced after retries."""


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY:
            raise GeminiAnalysisError(
                "GEMINI_API_KEY is not set on the server. "
                "Add it to backend/.env and restart the server."
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


# The JSON schema Gemini must produce. We describe it in the prompt itself
# (Gemini's JSON mode follows the described shape closely when it's this
# explicit) and then validate it in Python with Pydantic as the real gate.
RESPONSE_SCHEMA_DESCRIPTION = """
Return ONLY a JSON object with EXACTLY this shape (no markdown, no comments):

{
  "overall_score": <integer 0-100>,
  "section_breakdown": {
    "contact_info": {"score": <0-100>, "comment": "<short comment>"},
    "summary":      {"score": <0-100>, "comment": "<short comment>"},
    "experience":   {"score": <0-100>, "comment": "<short comment>"},
    "education":    {"score": <0-100>, "comment": "<short comment>"},
    "skills":       {"score": <0-100>, "comment": "<short comment>"},
    "formatting":   {"score": <0-100>, "comment": "<short comment>"}
  },
  "strengths": ["<3 to 5 short bullet points>"],
  "weaknesses": ["<3 to 5 short bullet points>"],
  "ats_score": <integer 0-100>,
  "ats_issues": ["<specific formatting/structure issues that would break ATS parsing, e.g. tables, columns, images, headers/footers, non-standard section titles, missing keywords>"],
  "human_touch_score": <integer 0-100, where 0 = extremely generic/templated/AI-sounding and 100 = distinctly personal and natural>,
  "human_touch_comment": "<one or two sentences explaining the human_touch_score>",
  "suggested_rewrite": {
    "section_name": "<name of the weakest section>",
    "original_excerpt": "<short excerpt of the original weak text, or empty string if not applicable>",
    "rewritten_text": "<an improved rewrite of that section>"
  },
  "job_match": null
}

If a job description is supplied below, instead of null, fill job_match as:
{
  "match_score": <integer 0-100>,
  "matched_keywords": ["<keywords/skills from the JD found in the CV>"],
  "missing_keywords": ["<important keywords/skills from the JD NOT found in the CV>"],
  "notes": "<1-2 sentence summary of fit>"
}
"""

SYSTEM_INSTRUCTION = (
    "You are an expert technical recruiter and ATS (Applicant Tracking System) "
    "specialist with 15 years of experience reviewing resumes across tech, "
    "finance, and general industries. You give honest, specific, actionable "
    "feedback — never generic filler. You always respond with strict JSON "
    "matching the schema you are given, and nothing else."
)


def build_prompt(cv_text: str, job_description: Optional[str] = None) -> str:
    jd_block = ""
    if job_description and job_description.strip():
        jd_block = (
            "\n\nJOB DESCRIPTION TO COMPARE AGAINST:\n"
            "-----\n"
            f"{job_description.strip()[:6000]}\n"
            "-----\n"
            "Use this job description to populate the job_match field."
        )
    else:
        jd_block = "\n\nNo job description was supplied. Set job_match to null."

    prompt = (
        "Analyze the following CV/resume text and evaluate it thoroughly.\n"
        f"{RESPONSE_SCHEMA_DESCRIPTION}\n"
        "Scoring guidance:\n"
        "- overall_score reflects general quality and job-readiness.\n"
        "- ats_score reflects how reliably an ATS parser could extract "
        "structured fields (contact, dates, titles, skills) from this text.\n"
        "- human_touch_score should be LOW for generic buzzword-stuffed, "
        "obviously templated text, and HIGH for specific, personal, "
        "achievement-driven writing with concrete numbers and context.\n"
        "- Be specific in every comment and bullet point; reference actual "
        "content from the CV rather than generic advice.\n"
        f"{jd_block}\n\n"
        "CV TEXT:\n"
        "-----\n"
        f"{cv_text[:15000]}\n"
        "-----\n"
    )
    return prompt


def _call_gemini_once(prompt: str) -> str:
    """Single call to Gemini, returns raw text. Raises on API-level errors."""
    _ensure_configured()

    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
    )

    generation_config = genai.types.GenerationConfig(
        temperature=settings.GEMINI_TEMPERATURE,
        response_mime_type="application/json",
    )

    response = model.generate_content(
        prompt,
        generation_config=generation_config,
    )

    # Safety blocks: Gemini returns a response with no candidates/parts,
    # or a finish_reason indicating SAFETY, instead of raising.
    if not response.candidates:
        raise GeminiAnalysisError(
            "Gemini returned no candidates (likely blocked by safety filters)."
        )

    candidate = response.candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    # finish_reason enum: 1=STOP, 2=MAX_TOKENS, 3=SAFETY, 4=RECITATION, 5=OTHER
    if finish_reason is not None and str(finish_reason).upper().endswith("SAFETY"):
        raise GeminiAnalysisError(
            "Gemini blocked this content due to safety filters. "
            "Try re-uploading with any unusual/sensitive content removed."
        )

    try:
        text = response.text
    except Exception as e:
        raise GeminiAnalysisError(f"Gemini response had no usable text: {e}") from e

    if not text or not text.strip():
        raise GeminiAnalysisError("Gemini returned an empty response.")

    return text


def _parse_and_validate(raw_text: str) -> AnalysisResult:
    """Parse JSON and validate against our schema. Raises on failure."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise GeminiAnalysisError(f"Gemini response was not valid JSON: {e}") from e

    try:
        return AnalysisResult.model_validate(data)
    except ValidationError as e:
        raise GeminiAnalysisError(f"Gemini JSON did not match expected schema: {e}") from e


def analyze_cv(cv_text: str, job_description: Optional[str] = None) -> AnalysisResult:
    """
    Main entry point: build prompt, call Gemini, validate JSON.
    Retries ONCE on rate limits, safety blocks, or malformed/invalid JSON,
    then fails gracefully with a clear error.
    """
    prompt = build_prompt(cv_text, job_description)

    last_error: Optional[Exception] = None

    for attempt in range(1, 3):  # attempt 1, then 1 retry (attempt 2)
        try:
            raw = _call_gemini_once(prompt)
            result = _parse_and_validate(raw)
            return result

        except google_exceptions.ResourceExhausted as e:
            # HTTP 429 - rate limit
            last_error = e
            logger.warning("Gemini rate limit hit (attempt %s): %s", attempt, e)
            if attempt < 2:
                time.sleep(2 * attempt)  # small backoff before retry
                continue

        except google_exceptions.GoogleAPIError as e:
            last_error = e
            logger.warning("Gemini API error (attempt %s): %s", attempt, e)
            if attempt < 2:
                time.sleep(1)
                continue

        except GeminiAnalysisError as e:
            last_error = e
            logger.warning("Gemini analysis error (attempt %s): %s", attempt, e)
            if attempt < 2:
                time.sleep(1)
                continue

        except Exception as e:  # noqa: BLE001 - last line of defense
            last_error = e
            logger.exception("Unexpected error calling Gemini (attempt %s)", attempt)
            if attempt < 2:
                time.sleep(1)
                continue

    # Both attempts failed
    raise GeminiAnalysisError(
        f"CV analysis failed after retrying once. Last error: {last_error}"
    )
