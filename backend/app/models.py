"""
Pydantic models shared across the app: the shape of what Gemini must
return, and the shape of what the API sends back to the frontend.
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class SectionScore(BaseModel):
    score: int = Field(ge=0, le=100)
    comment: str = ""


class SectionBreakdown(BaseModel):
    contact_info: SectionScore
    summary: SectionScore
    experience: SectionScore
    education: SectionScore
    skills: SectionScore
    formatting: SectionScore


class SuggestedRewrite(BaseModel):
    section_name: str
    original_excerpt: str = ""
    rewritten_text: str


class JobMatch(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_keywords: List[str] = []
    missing_keywords: List[str] = []
    notes: str = ""


class AnalysisResult(BaseModel):
    """The strict JSON contract we ask Gemini to fill in."""
    overall_score: int = Field(ge=0, le=100)
    section_breakdown: SectionBreakdown
    strengths: List[str]
    weaknesses: List[str]
    ats_score: int = Field(ge=0, le=100)
    ats_issues: List[str]
    human_touch_score: int = Field(ge=0, le=100)
    human_touch_comment: str = ""
    suggested_rewrite: SuggestedRewrite
    job_match: Optional[JobMatch] = None


class AnalysisRecord(BaseModel):
    """What actually gets stored in / read from MongoDB."""
    id: str
    session_id: str
    filename: str
    created_at: str
    analysis: AnalysisResult
    raw_text_char_count: int
    job_description_provided: bool = False


class AnalysisListItem(BaseModel):
    """Lightweight shape for history listings (no full analysis payload)."""
    id: str
    filename: str
    created_at: str
    overall_score: int
    ats_score: int
    human_touch_score: int
