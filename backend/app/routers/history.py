"""
Routes for viewing analysis history for a given session/user id.
"""
from fastapi import APIRouter

from app import database

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 50):
    items = await database.list_analyses_for_session(session_id, limit=limit)
    return {"session_id": session_id, "count": len(items), "items": items}
