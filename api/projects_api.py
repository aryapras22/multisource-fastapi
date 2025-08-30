import datetime
import uuid
import asyncio
from fastapi import APIRouter, HTTPException
from pymongo import ReturnDocument
from typing import List, Dict, Any
from bson.objectid import ObjectId
from db import project_collection
from models import (
    CreateProjectRequest,
    ProjectDataSources,
    ProjectFetchState,
    ProjectModel,
    UpdateFetchStateRequest,
    UpdateProjectConfigRequest,
    UpdateProjectStatusRequest,
)
from db import (
    project_collection,
    apps_collection,
    reviews_collection,
    news_collection,
    tweets_collection,
    user_stories_collection,
    use_cases_collection,
    ai_stories_collection,
    ai_use_cases_collection,
)
from services.get_queries import generate_queries_from_case_study

router = APIRouter()


@router.get("/get-projects", response_model=list[ProjectModel])
async def get_projects():
    projects_cursor = project_collection.find({})
    projects_list = list(projects_cursor)
    for project in projects_list:
        if isinstance(project.get("created_at"), datetime.datetime):
            project["created_at"] = project["created_at"]
        project.setdefault("status", "draft")
        project.setdefault("queries", [])
        project.setdefault("dataSources", ProjectDataSources().model_dump())
        project.setdefault("fetchState", ProjectFetchState().model_dump())
    return projects_list


@router.get("/get-project-data", response_model=ProjectModel)
async def get_project_data(id: str):
    doc = project_collection.find_one({"_id": id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    doc.setdefault("queries", [])
    doc.setdefault("dataSources", ProjectDataSources().model_dump())
    doc.setdefault("status", "draft")
    doc.setdefault("fetchState", ProjectFetchState().model_dump())
    return doc


@router.post("/create-new-project")
async def create_project(request: CreateProjectRequest) -> dict:
    project_id = str(uuid.uuid4())
    queries = await generate_queries_from_case_study(case_study=request.case_study)
    case_study_data = {
        "_id": project_id,
        "name": request.name,
        "case_study": request.case_study,
        "description": request.description,
        "queries": queries,
        "created_at": datetime.datetime.now(),
        "status": "draft",
        "dataSources": (request.dataSources or ProjectDataSources()).model_dump(),
        "fetchState": ProjectFetchState().model_dump(),
    }
    project_collection.insert_one(case_study_data)
    return {
        "project_id": project_id,
        "queries": queries,
        "dataSources": case_study_data["dataSources"],
        "fetchState": case_study_data["fetchState"],
    }


@router.patch("/update-project-config", response_model=ProjectModel)
async def update_project_config(payload: UpdateProjectConfigRequest):
    update: dict = {}
    if payload.queries is not None:
        update["queries"] = payload.queries
    if payload.dataSources is not None:
        update["dataSources"] = payload.dataSources.model_dump()
    if payload.description is not None:
        update["description"] = payload.description
    if not update:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    update["status"] = "configured"
    doc = project_collection.find_one_and_update(
        {"_id": payload.id},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    doc.setdefault("queries", [])
    doc.setdefault("dataSources", ProjectDataSources().model_dump())
    doc.setdefault("fetchState", ProjectFetchState().model_dump())
    doc.setdefault("status", "draft")
    return doc


@router.get("/check-project-fetch-states", response_model=ProjectFetchState)
def check_project_fetch_state(project_id: str):
    project = project_collection.find_one({"_id": project_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.get("fetchState", ProjectFetchState().model_dump())


@router.post("/update-project-fetch-state")
def update_project_fetch_state(payload: UpdateFetchStateRequest):
    allowed_keys = [
        "appStores",
        "news",
        "socialMedia",
        "reviews",
        "userStories",
        "useCase",
        "aiUserStories",
        "aiUseCase",
    ]
    set_ops = {}
    for k in allowed_keys:
        v = getattr(payload, k)
        if v is not None:
            set_ops[f"fetchState.{k}"] = v
    if not set_ops:
        raise HTTPException(status_code=400, detail="No fetchState fields provided")
    result = project_collection.update_one(
        {"_id": payload.project_id}, {"$set": set_ops}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_collection.find_one({"_id": payload.project_id})
    return project.get("fetchState", ProjectFetchState().model_dump())  # type: ignore


@router.get("/get-project-queries", response_model=list[str])
async def get_project_queries(project_id: str):
    doc = project_collection.find_one({"_id": project_id}, {"queries": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    queries = doc.get("queries") or []
    return queries


@router.patch("/update-project-status", response_model=ProjectModel)
async def update_project_status(payload: UpdateProjectStatusRequest):
    """
    Memperbarui status proyek tertentu.
    """
    updated_project = project_collection.find_one_and_update(
        {"_id": payload.project_id},
        {"$set": {"status": payload.status}},
        return_document=ReturnDocument.AFTER,
    )

    if not updated_project:
        raise HTTPException(
            status_code=404,
            detail=f"Proyek dengan id '{payload.project_id}' tidak ditemukan",
        )

    # Pastikan field default ada untuk konsistensi respons
    updated_project.setdefault("queries", [])
    updated_project.setdefault("dataSources", ProjectDataSources().model_dump())
    updated_project.setdefault("fetchState", ProjectFetchState().model_dump())

    return updated_project


def serialize_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converts ObjectId to string for a list of documents."""
    for doc in docs:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
    return docs


@router.get("/projects/{project_id}/apps", response_model=List[Dict[str, Any]])
def get_project_apps(project_id: str):
    docs = list(apps_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/reviews", response_model=List[Dict[str, Any]])
def get_project_reviews(project_id: str):
    docs = list(reviews_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/news", response_model=List[Dict[str, Any]])
def get_project_news(project_id: str):
    docs = list(news_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/tweets", response_model=List[Dict[str, Any]])
def get_project_tweets(project_id: str):
    docs = list(tweets_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/user-stories", response_model=List[Dict[str, Any]])
def get_project_user_stories(project_id: str):
    docs = list(user_stories_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/use-cases", response_model=List[Dict[str, Any]])
def get_project_use_cases(project_id: str):
    docs = list(use_cases_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/ai-stories", response_model=List[Dict[str, Any]])
def get_project_ai_stories(project_id: str):
    docs = list(ai_stories_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/ai-use-cases", response_model=List[Dict[str, Any]])
def get_project_ai_use_cases(project_id: str):
    docs = list(ai_use_cases_collection.find({"project_id": project_id}))
    return serialize_docs(docs)


@router.get("/projects/{project_id}/all-data", response_model=Dict[str, Any])
def get_all_project_data(project_id: str):
    """
    Fetches all data (project details, apps, reviews, news, tweets, user stories, use cases, ai stories, ai use cases)
    for a given project_id from their respective collections.
    """
    query = {"project_id": project_id}
    project_doc = project_collection.find_one({"_id": project_id})
    if not project_doc:
        raise HTTPException(status_code=404, detail="Project not found")
    # Convert ObjectId to string for _id
    if "_id" in project_doc:
        project_doc["_id"] = str(project_doc["_id"])
    project_doc.setdefault("queries", [])
    project_doc.setdefault("dataSources", ProjectDataSources().model_dump())
    project_doc.setdefault("fetchState", ProjectFetchState().model_dump())
    project_doc.setdefault("status", "draft")

    data = {
        "project": project_doc,
        "apps": serialize_docs(list(apps_collection.find(query))),
        "reviews": serialize_docs(list(reviews_collection.find(query))),
        "news": serialize_docs(list(news_collection.find(query))),
        "tweets": serialize_docs(list(tweets_collection.find(query))),
        "user_stories": serialize_docs(list(user_stories_collection.find(query))),
        "use_cases": serialize_docs(list(use_cases_collection.find(query))),
        "ai_stories": serialize_docs(list(ai_stories_collection.find(query))),
        "ai_use_cases": serialize_docs(list(ai_use_cases_collection.find(query))),
    }
    return data
