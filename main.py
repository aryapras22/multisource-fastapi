from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from models import AppModel, CaseStudyRequest, UpdateQueriesRequest, ReviewModel
from services.get_queries import generate_queries_from_case_study
from services.app_scrapper import (
    get_google_play_apps,
    get_appstore_apps,
    get_google_play_reviews,
    get_appstore_reviews,
)
import asyncio
import uuid
from db import case_study_collection, apps_collection, reviews_collection
from pymongo.errors import DuplicateKeyError


app = FastAPI()

origins = [settings.frontend_origin]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/get-queries")
async def get_queries(request: CaseStudyRequest) -> dict:
    session_id = str(uuid.uuid4())
    queries = await generate_queries_from_case_study(case_study=request.case_study)

    case_study_data = {
        "_id": session_id,
        "case_study": request.case_study,
        "queries": queries,
    }
    case_study_collection.insert_one(case_study_data)

    return {"session_id": session_id, "queries": queries}


@app.post("/update-queries")
async def update_queries(request: UpdateQueriesRequest) -> dict:
    """
    Update the queries for a specific session after user selection.

    This allows users to select which queries they want to use before
    fetching apps with the /get-apps endpoint.
    """
    case_study_data = case_study_collection.find_one({"_id": request.session_id})
    if not case_study_data:
        raise HTTPException(status_code=404, detail="Session ID not found")

    # Update the queries in the database with only the selected ones
    case_study_collection.update_one(
        {"_id": request.session_id}, {"$set": {"queries": request.queries}}
    )

    return {"session_id": request.session_id, "updated_queries": request.queries}


@app.get("/get-apps", response_model=list[AppModel])
async def get_apps(session_id: str, limit: int = 10) -> list:
    """
    Get apps from Google Play and Apple App Store concurrently based on a session_id.
    """
    case_study_data = case_study_collection.find_one({"_id": session_id})
    if not case_study_data:
        raise HTTPException(status_code=404, detail="Session ID not found")

    apps_list = list(apps_collection.find({"session_id": session_id}))
    if apps_list:
        return apps_list

    queries = case_study_data.get("queries", [])
    tasks = []
    for query in queries:
        tasks.append(asyncio.to_thread(get_google_play_apps, query, limit=limit))
        tasks.append(asyncio.to_thread(get_appstore_apps, query, limit=limit))

    results = await asyncio.gather(*tasks)

    all_apps = []
    # Flatten the list of lists and add store info
    for i, query_apps in enumerate(results):
        store = "google" if i % 2 == 0 else "apple"
        for app in query_apps:
            app["store"] = store
            app["session_id"] = session_id
            all_apps.append(app)

    unique_apps_dict = {(app["appId"], app["store"]): app for app in all_apps}
    unique_apps_list = list(unique_apps_dict.values())

    if unique_apps_list:
        try:
            # Create a copy for database insertion to avoid ObjectId in response
            db_apps = [app.copy() for app in unique_apps_list]
            apps_collection.insert_many(db_apps)
        except DuplicateKeyError:
            # Handle cases where apps might already exist if the endpoint is called multiple times
            pass

    return unique_apps_list


@app.get("/get-reviews", response_model=list[ReviewModel])
async def get_reviews(
    session_id: str,
    store: str,
    app_id: str,
    count: int = 10,
) -> list[ReviewModel]:
    """
    Get reviews for a specific app and save them to the database.
    """

    reviews = []
    if store == "google":
        reviews = await asyncio.to_thread(get_google_play_reviews, app_id, count=count)
    elif store == "apple":
        reviews = await asyncio.to_thread(get_appstore_reviews, app_id, count=count)
    else:
        raise HTTPException(
            status_code=400, detail="Invalid store specified. Use 'google' or 'apple'."
        )

    if reviews:
        for review in reviews:
            review["app_id"] = app_id
            review["store"] = store
            review["session_id"] = session_id
        reviews_collection.insert_many(reviews)

    return reviews


# @app.get("/get-news")
# async def get_news():
