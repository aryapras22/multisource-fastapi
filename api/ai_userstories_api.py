from fastapi import APIRouter, HTTPException
from models import (
    AIUserStoryDocOut,
    GenerateAIUserStoriesRequest,
    GenerateAIUserStoriesResponse,
    AIUserStoryItem,
    SourceInfo,
)
from services.ai_requirement_service import generate_userstory_with_ai
from db import (
    ai_stories_collection,
    reviews_collection,
    news_collection,
    tweets_collection,
)
import uuid
from datetime import datetime
from bson.objectid import ObjectId
from pydantic import BaseModel


class AIUserStoryWithSourceOut(AIUserStoryDocOut):
    source_data: SourceInfo


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
            doc_to_save = {
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
            if item.field_insight:
                doc_to_save["field_insight"] = item.field_insight.model_dump()
            docs.append(doc_to_save)

    if payload.persist and docs:
        ai_stories_collection.insert_many(docs)

    for s in docs:
        # Normalize data
        s["_id"] = str(s["_id"])
        s.setdefault("why", None)
        s.setdefault("content_type", None)
        s.setdefault("confidence", 0.0)
        s.setdefault("field_insight", None)

        ctype = s.get("content_type")
        cid = str(s.get("content_id", ""))

    return GenerateAIUserStoriesResponse(
        project_id=payload.project_id,
        content_id=payload.content_id,
        count=len(stories),
        stories=stories,
    )


@router.get("/user-stories", response_model=list[AIUserStoryWithSourceOut])
async def list_ai_user_stories(project_id: str):
    q = {"project_id": project_id}
    docs = list(ai_stories_collection.find(q).sort("created_at", -1))

    if not docs:
        return []

    # Group content_ids by content_type
    ids_by_type = {"review": set(), "news": set(), "tweet": set()}
    for s in docs:
        cid = str(s.get("content_id", ""))
        ctype = s.get("content_type")
        if ctype in ids_by_type and cid:
            ids_by_type[ctype].add(cid)

    # Helper function to fetch source documents by ID
    def _fetch_many(coll, raw_ids: set[str]):
        if not raw_ids:
            return {}
        obj_ids = []
        str_ids = []
        for _id in raw_ids:
            if ObjectId.is_valid(_id):
                obj_ids.append(ObjectId(_id))
            str_ids.append(_id)
        # Try both ObjectId and string _id (in case some were stored as str)
        q = {"$or": [{"_id": {"$in": obj_ids}}] if obj_ids else []}
        q["$or"].append({"_id": {"$in": str_ids}})
        docs = list(coll.find({"$or": q["$or"]}))
        result = {}
        for d in docs:
            result[str(d["_id"])] = d
        return result

    # Fetch source content data
    review_docs = _fetch_many(reviews_collection, ids_by_type["review"])
    news_docs = _fetch_many(news_collection, ids_by_type["news"])
    tweet_docs = _fetch_many(tweets_collection, ids_by_type["tweet"])

    # Build response with source data
    out = []
    for s in docs:
        # Normalize data
        s["_id"] = str(s["_id"])
        s.setdefault("why", None)
        s.setdefault("content_type", None)
        s.setdefault("confidence", 0.0)

        ctype = s.get("content_type")
        cid = str(s.get("content_id", ""))

        # Build source_data
        src_info: SourceInfo
        if ctype == "review":
            doc = review_docs.get(cid)
            if not doc:
                src_info = SourceInfo(
                    type="review",
                    title="(review)",
                    content="",
                )
            else:
                title = (doc.get("review") or "")[:60] or "(review)"
                src_info = SourceInfo(
                    type="review",
                    title=title,
                    author=doc.get("reviewer"),
                    content=doc.get("review") or "",
                    rating=(
                        float(doc.get("rating"))
                        if doc.get("rating") is not None
                        else None
                    ),
                )
        elif ctype == "news":
            doc = news_docs.get(cid)
            if not doc:
                src_info = SourceInfo(
                    type="news",
                    title="(news)",
                    content="",
                )
            else:
                src_info = SourceInfo(
                    type="news",
                    title=doc.get("title") or "(news)",
                    author=doc.get("author"),
                    content=doc.get("content") or (doc.get("description") or ""),
                    link=doc.get("link"),
                )
        elif ctype == "tweet":
            doc = tweet_docs.get(cid)
            if not doc:
                src_info = SourceInfo(
                    type="tweet",
                    title="(tweet)",
                    content="",
                )
            else:
                text = doc.get("text") or ""
                title = text[:60] or "(tweet)"
                author_obj = doc.get("author") or {}
                author_name = author_obj.get("username") or author_obj.get("name")
                src_info = SourceInfo(
                    type="tweet",
                    title=title,
                    author=author_name,
                    content=text,
                    link=doc.get("url"),
                )
        elif ctype == "raw" or not ctype:
            # For raw text input without a source document
            src_info = SourceInfo(
                type="review",  # Default type
                title="(Raw Input)",
                content=s.get("evidence", ""),
            )
        else:
            src_info = SourceInfo(
                type="review",
                title="(unknown)",
                content="",
            )

        try:
            base_story = AIUserStoryDocOut.model_validate(s)
            out.append(
                AIUserStoryWithSourceOut(
                    **base_story.model_dump(by_alias=True),
                    source_data=src_info,
                )
            )
        except Exception:
            continue

    # Sort by confidence score (highest first)
    out.sort(key=lambda x: x.confidence, reverse=True)
    return out
