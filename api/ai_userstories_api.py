from fastapi import APIRouter, HTTPException
from models import (
    AIUserStoryDocOut,
    GenerateAIUserStoriesRequest,
    GenerateAIUserStoriesResponse,
    AIUserStoryItem,
)
from services.ai_requirement_service import generate_userstory_with_ai
from db import ai_stories_collection
import uuid
from datetime import datetime

router = APIRouter(prefix="/ai", tags=["ai-userstories"])


@router.post("/generate-user-stories", response_model=GenerateAIUserStoriesResponse)
async def generate_ai_user_stories(payload: GenerateAIUserStoriesRequest):
    if payload.persist and not payload.project_id:
        raise HTTPException(
            status_code=400,
            detail="project_id required when persist=True",
        )
    stories_raw = await generate_userstory_with_ai(
        payload.content_type, payload.content
    )

    stories = []
    docs = []
    for s in stories_raw:
        if payload.content_id and "content_id" not in s:
            s["content_id"] = payload.content_id
        item = AIUserStoryItem(**s)
        stories.append(item)
        if payload.persist:
            docs.append(
                {
                    "_id": str(uuid.uuid4()),
                    "who": item.who,
                    "what": item.what,
                    "why": item.why,
                    "as_a_i_want_so_that": item.as_a_i_want_so_that,
                    "evidence": item.evidence,
                    "sentiment": item.sentiment,
                    "confidence": item.confidence,
                    "content_type": payload.content_type,
                    "content_id": payload.content_id,
                    "project_id": payload.project_id,
                    "created_at": datetime.utcnow(),
                }
            )

    if payload.persist and docs:
        ai_stories_collection.insert_many(docs)

    return GenerateAIUserStoriesResponse(
        project_id=payload.project_id,
        content_id=payload.content_id,
        count=len(stories),
        stories=stories,
    )


@router.get("/user-stories", response_model=list[AIUserStoryDocOut])
async def list_ai_user_stories(project_id: str):
    q = {"project_id": project_id}
    docs = list(ai_stories_collection.find(q).sort("created_at", -1))
    out: list[AIUserStoryDocOut] = []
    for d in docs:
        # Backward compatibility / defaults
        d.setdefault("why", None)
        d.setdefault("content_type", None)
        try:
            d["_id"] = str(d["_id"])
            out.append(AIUserStoryDocOut.model_validate(d))
        except Exception:
            continue
    return out
