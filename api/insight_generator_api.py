from fastapi import APIRouter, HTTPException
from services.generative_service import generate_insight_for_story
from db import user_stories_collection
from models import Insight
from pydantic import BaseModel
from bson.objectid import ObjectId

router = APIRouter(prefix="/stories", tags=["user-stories"])


class GenerateInsightResponse(BaseModel):
    story_id: str
    project_id: str
    insight: Insight


@router.post("/generate-insight/{story_id}", response_model=GenerateInsightResponse)
async def generate_story_insight(story_id: str):
    """
    Menghasilkan wawasan strategis untuk satu cerita pengguna (user story)
    dan menambahkannya ke dokumen tersebut.
    """
    try:
        obj_id = story_id
    except Exception:
        raise HTTPException(status_code=400, detail="Format story_id tidak valid")

    story = user_stories_collection.find_one({"_id": obj_id})

    if not story:
        raise HTTPException(
            status_code=404,
            detail=f"Cerita pengguna dengan id '{story_id}' tidak ditemukan",
        )

    story_for_ai = {
        "who": story.get("who"),
        "what": story.get("what"),
        "why": story.get("why"),
        "full_sentence": story.get("full_sentence"),
    }

    insight_data = await generate_insight_for_story(story_for_ai)

    try:
        insight = Insight.model_validate(insight_data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Menerima format wawasan yang tidak valid dari layanan AI: {e}",
        )

    update_result = user_stories_collection.update_one(
        {"_id": obj_id}, {"$set": {"insight": insight.model_dump()}}
    )

    if update_result.modified_count == 0:
        pass

    return GenerateInsightResponse(
        story_id=story_id,
        project_id=str(story.get("project_id")),
        insight=insight,
    )
