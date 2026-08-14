"""
MongoDB storage module.

Isolated from HTTP and Gemini logic. Uses Motor (async PyMongo) so it
plays nicely with FastAPI's async request handlers.
"""
import datetime
import logging
import uuid
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.models import AnalysisResult, AnalysisRecord, AnalysisListItem

logger = logging.getLogger("cv_analyzer.database")

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI)
    return _client


def get_db():
    return get_client()[settings.MONGO_DB_NAME]


def get_collection():
    return get_db()["analyses"]


async def ensure_indexes() -> None:
    """Create indexes used for history lookups. Safe to call every startup."""
    collection = get_collection()
    await collection.create_index("session_id")
    await collection.create_index("created_at")


async def ping() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception as e:
        logger.error("MongoDB ping failed: %s", e)
        return False


async def save_analysis(
    session_id: str,
    filename: str,
    analysis: AnalysisResult,
    raw_text_char_count: int,
    job_description_provided: bool = False,
) -> AnalysisRecord:
    doc_id = str(uuid.uuid4())
    created_at = datetime.datetime.utcnow().isoformat() + "Z"

    document = {
        "_id": doc_id,
        "session_id": session_id,
        "filename": filename,
        "created_at": created_at,
        "analysis": analysis.model_dump(),
        "raw_text_char_count": raw_text_char_count,
        "job_description_provided": job_description_provided,
    }

    await get_collection().insert_one(document)

    return AnalysisRecord(
        id=doc_id,
        session_id=session_id,
        filename=filename,
        created_at=created_at,
        analysis=analysis,
        raw_text_char_count=raw_text_char_count,
        job_description_provided=job_description_provided,
    )


async def get_analysis_by_id(analysis_id: str) -> Optional[AnalysisRecord]:
    doc = await get_collection().find_one({"_id": analysis_id})
    if not doc:
        return None
    return AnalysisRecord(
        id=doc["_id"],
        session_id=doc["session_id"],
        filename=doc["filename"],
        created_at=doc["created_at"],
        analysis=AnalysisResult.model_validate(doc["analysis"]),
        raw_text_char_count=doc.get("raw_text_char_count", 0),
        job_description_provided=doc.get("job_description_provided", False),
    )


async def list_analyses_for_session(
    session_id: str, limit: int = 50
) -> List[AnalysisListItem]:
    cursor = (
        get_collection()
        .find({"session_id": session_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    items: List[AnalysisListItem] = []
    async for doc in cursor:
        analysis = doc["analysis"]
        items.append(
            AnalysisListItem(
                id=doc["_id"],
                filename=doc["filename"],
                created_at=doc["created_at"],
                overall_score=analysis.get("overall_score", 0),
                ats_score=analysis.get("ats_score", 0),
                human_touch_score=analysis.get("human_touch_score", 0),
            )
        )
    return items


async def delete_analysis(analysis_id: str, session_id: str) -> bool:
    """Delete only if it belongs to the requesting session."""
    result = await get_collection().delete_one(
        {"_id": analysis_id, "session_id": session_id}
    )
    return result.deleted_count > 0
