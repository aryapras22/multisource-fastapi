from fastapi import APIRouter, HTTPException
from bson.objectid import ObjectId

from db import (
    reviews_collection,
    news_collection,
    tweets_collection,
    user_stories_collection,
)
from models import (
    ExtractRequest,
    StoryOut,
    StoryWithSourceOut,
    SourceInfo,
    _to_story_out,
)
from services.user_story_extractor import extract_user_stories

router = APIRouter()


# Helper function to fetch multiple documents by ObjectId
def _fetch_many(coll, obj_ids: set[ObjectId]):
    """Fetch multiple documents from a collection by their ObjectIds.
    
    Args:
        coll: MongoDB collection
        obj_ids: Set of ObjectIds to fetch
        
    Returns:
        Dictionary mapping string IDs to documents
    """
    if not obj_ids:
        return {}
    docs = list(coll.find({"_id": {"$in": list(obj_ids)}}))
    return {str(d["_id"]): d for d in docs}


@router.post("/extract-user-story", response_model=list[StoryOut])
def extract_user_story(req: ExtractRequest):
    try:
        models = extract_user_stories(
            source=req.source,
            source_id=req.source_id,
            content=req.content,
            project_id=req.project_id,
            min_similarity=req.min_similarity,
            dedupe=req.dedupe,
        )
        return [_to_story_out(m) for m in models]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


@router.post("/backfill-user-story-project-ids")
def backfill_user_story_project_ids():
    updated = 0
    cursor = user_stories_collection.find({"project_id": {"$exists": False}})
    for us in cursor:
        src = us.get("source")
        sid = us.get("source_id")
        proj_id = None
        doc = None
        if sid and ObjectId.is_valid(str(sid)):
            obj_id = ObjectId(sid)
            if src == "review":
                doc = reviews_collection.find_one({"_id": obj_id})
            elif src == "news":
                doc = news_collection.find_one({"_id": obj_id})
            elif src == "tweet":
                doc = tweets_collection.find_one({"_id": obj_id})
        if doc:
            proj_id = doc.get("project_id")
        if proj_id:
            user_stories_collection.update_one(
                {"_id": us["_id"]}, {"$set": {"project_id": proj_id}}
            )
            updated += 1
    return {"updated": updated}


@router.get("/get-project-user-stories", response_model=list[StoryWithSourceOut])
def get_project_user_stories(project_id: str):
    stories_cur = user_stories_collection.find({"project_id": project_id})
    stories_raw = list(stories_cur)
    if not stories_raw:
        return []

    ids_by_type: dict[str, set[ObjectId]] = {
        "review": set(),
        "news": set(),
        "tweet": set(),
    }
    for s in stories_raw:
        sid = str(s.get("source_id", ""))
        stype = s.get("source")
        if stype in ids_by_type and sid and ObjectId.is_valid(sid):
            ids_by_type[stype].add(ObjectId(sid))

    review_docs = _fetch_many(reviews_collection, ids_by_type["review"])
    news_docs = _fetch_many(news_collection, ids_by_type["news"])
    tweet_docs = _fetch_many(tweets_collection, ids_by_type["tweet"])

    out: list[StoryWithSourceOut] = []
    for s in stories_raw:
        s["_id"] = str(s["_id"])
        s.setdefault("why", None)
        s.setdefault("similarity_score", s.get("similarity", 0.0))

        stype: str = s.get("source", "")
        sid = str(s.get("source_id", ""))
        doc = None
        src_info: SourceInfo

        if stype == "review":
            doc = review_docs.get(sid)
            title = (doc.get("review", "")[:60] if doc else "") or "(review)"
            src_info = SourceInfo(
                type="review",
                title=title,
                author=doc.get("reviewer") if doc else None,
                content=doc.get("review", "") if doc else "",
                rating=(
                    float(doc["rating"])
                    if doc and doc.get("rating") is not None
                    else None
                ),
            )
        elif stype == "news":
            doc = news_docs.get(sid)
            src_info = SourceInfo(
                type="news",
                title=(doc.get("title") if doc else None) or "(news)",
                author=doc.get("author") if doc else None,
                content=(
                    (doc.get("content") or doc.get("description", "")) if doc else ""
                ),
                link=doc.get("link") if doc else None,
            )
        elif stype == "tweet":
            doc = tweet_docs.get(sid)
            text = (doc.get("text", "") if doc else "") or ""
            title = text[:60] or "(tweet)"
            author_obj = (doc.get("author", {}) if doc else {}) or {}
            author = author_obj.get("username") or author_obj.get("name")
            src_info = SourceInfo(
                type="tweet",
                title=title,
                author=author,
                content=text,
                link=doc.get("url") if doc else None,
            )
        else:
            src_info = SourceInfo(type="review", title="(unknown)", content="")

        try:
            base_story = StoryOut.model_validate(s)
            out.append(
                StoryWithSourceOut(
                    **base_story.model_dump(by_alias=True), source_data=src_info
                )
            )
        except Exception:
            continue

    out.sort(key=lambda x: x.similarity_score, reverse=True)
    return out


@router.post("/clean-duplicates")
def clean_duplicate_user_stories(project_id: str):
    """
    Finds and removes duplicate user stories for a given project.
    A duplicate is defined as a story with the same 'source' and 'what'.
    For each group of duplicates, one is kept and the others are deleted.
    """
    pipeline = [
        {"$match": {"project_id": project_id}},
        {
            "$group": {
                "_id": {"source": "$source", "what": "$what"},
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
    ]

    duplicates = user_stories_collection.aggregate(pipeline)

    ids_to_delete = []
    for group in duplicates:
        # Keep the first document, mark the rest for deletion
        ids_to_delete.extend(group["ids"][1:])

    deleted_count = 0
    if ids_to_delete:
        result = user_stories_collection.delete_many({"_id": {"$in": ids_to_delete}})
        deleted_count = result.deleted_count

    return {"deleted_count": deleted_count}


@router.get("/get-project-user-story-ids", response_model=list[str])
def get_project_user_story_ids(project_id: str):
    """
    Mengambil hanya ID dari cerita pengguna untuk project_id yang diberikan.
    """
    cursor = user_stories_collection.find(
        {"project_id": project_id},
        {"_id": 1},  # Proyeksi untuk hanya mendapatkan field _id
    )
    ids = [str(doc["_id"]) for doc in cursor]
    return ids
