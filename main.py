import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from models import (
    AppModel,
    ExtractRequest,
    NewsModel,
    ReviewModel,
    StoryOut,
    TwitterModel,
    ProjectModel,
    CreateProjectRequest,
    ProjectDataSources,
    UpdateProjectConfigRequest,
    ProjectFetchState,
    _to_story_out,  # added
)
from services.get_queries import generate_queries_from_case_study
from services.app_scrapper import (
    get_google_play_apps,
    get_appstore_apps,
    get_google_play_reviews,
    get_appstore_reviews,
)
from services.news_scrapper import scrap_news
import asyncio
import uuid
from db import (
    project_collection,
    apps_collection,
    reviews_collection,
    news_collection,
    tweets_collection,
)
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument
from services.preprocessing import clean_news_content, clean_review, clean_tweet_text
from services.twitter_x_scrapper import scrap_twitter_x
from bson.objectid import ObjectId

from services.user_story_extractor import extract_user_stories


app = FastAPI()

origins = [settings.frontend_origin, "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/get-projects", response_model=list[ProjectModel])
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


@app.get("/get-project-data", response_model=ProjectModel)
async def get_project_data(id: str):
    doc = project_collection.find_one({"_id": id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    doc.setdefault("queries", [])
    doc.setdefault("dataSources", ProjectDataSources().model_dump())
    doc.setdefault("status", "draft")
    doc.setdefault("fetchState", ProjectFetchState().model_dump())
    return doc


@app.post("/create-new-project")
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


@app.patch("/update-project-config", response_model=ProjectModel)
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


@app.get("/check-project-fetch-states", response_model=ProjectFetchState)
def check_project_fetch_state(project_id: str):
    project = project_collection.find_one({"_id": project_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.get("fetchState", ProjectFetchState().model_dump())


@app.get("/get-project-queries", response_model=list[str])
async def get_project_queries(project_id: str):
    doc = project_collection.find_one({"_id": project_id}, {"queries": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    queries = doc.get("queries") or []
    return queries


@app.get("/get-project-apps", response_model=list[AppModel])
def get_project_apps(project_id: str) -> list:
    doc = apps_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Apps not found")

    return list(doc)


@app.get("/get-project-app-reviews", response_model=list[ReviewModel])
def get_project_app_reviews(project_id: str) -> list:
    doc = reviews_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Reviews not found")

    return list(doc)


@app.get("/get-project-news", response_model=list[NewsModel])
def get_project_news(project_id: str) -> list:
    doc = news_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="News not found")
    return list(doc)


@app.get("/get-project-tweets", response_model=list[TwitterModel])
def get_project_tweets(project_id: str) -> list:
    doc = tweets_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Tweets not found")

    return list(doc)


@app.get("/get-apps", response_model=list[AppModel])
async def get_apps(project_id: str, limit: int = 10) -> list:
    case_study_data = project_collection.find_one({"_id": project_id})
    if not case_study_data:
        raise HTTPException(status_code=404, detail="Project ID not found")
    apps_list = list(apps_collection.find({"project_id": project_id}))
    if apps_list:
        # ensure fetchState updated if not already
        if not case_study_data.get("fetchState", {}).get("appStores"):
            project_collection.update_one(
                {"_id": project_id}, {"$set": {"fetchState.appStores": True}}
            )
        return apps_list
    queries = case_study_data.get("queries", [])
    tasks = []
    for query in queries:
        tasks.append(asyncio.to_thread(get_google_play_apps, query, limit=limit))
        tasks.append(asyncio.to_thread(get_appstore_apps, query, limit=limit))
    results = await asyncio.gather(*tasks)
    all_apps = []
    for i, query_apps in enumerate(results):
        store = "google" if i % 2 == 0 else "apple"
        for app in query_apps:
            app["store"] = store
            app["project_id"] = project_id
            all_apps.append(app)
    unique_apps_dict = {(app["appId"], app["store"]): app for app in all_apps}
    unique_apps_list = list(unique_apps_dict.values())
    if unique_apps_list:
        try:
            db_apps = [app.copy() for app in unique_apps_list]
            apps_collection.insert_many(db_apps)
            project_collection.update_one(
                {"_id": project_id}, {"$set": {"fetchState.appStores": True}}
            )
            app_list = list(apps_collection.find({"project_id": project_id}))
        except DuplicateKeyError:
            project_collection.update_one(
                {"_id": project_id}, {"$set": {"fetchState.appStores": True}}
            )
    return app_list


@app.get("/get-reviews", response_model=list[ReviewModel])
async def get_reviews(
    project_id: str,
    store: str,
    app_id: str,
    count: int = 10,
) -> list[ReviewModel]:
    # Attempt to reuse cached reviews
    existing = list(
        reviews_collection.find(
            {"project_id": project_id, "app_id": app_id, "store": store}
        )
    )
    if existing:
        project_collection.update_one(
            {"_id": project_id}, {"$set": {"fetchState.reviews": True}}
        )
        return existing

    if store == "google":
        reviews = await asyncio.to_thread(get_google_play_reviews, app_id, count=count)
    elif store == "apple":
        reviews = await asyncio.to_thread(get_appstore_reviews, app_id, count=count)
    else:
        raise HTTPException(status_code=400, detail="Invalid store (google|apple)")

    for r in reviews:
        r["app_id"] = app_id
        r["store"] = store
        r["project_id"] = project_id

    if reviews:
        reviews_collection.insert_many(reviews)
        project_collection.update_one(
            {"_id": project_id}, {"$set": {"fetchState.reviews": True}}
        )

    return reviews


@app.get("/get-news", response_model=list[NewsModel])
async def get_news(project_id: str, query: str, count: int = 10) -> list[NewsModel]:
    existing_articles = list(
        news_collection.find({"query": query, "project_id": project_id})
    )
    if existing_articles:
        project_collection.update_one(
            {"_id": project_id}, {"$set": {"fetchState.news": True}}
        )
        return existing_articles
    news = await asyncio.to_thread(scrap_news, query, count=count)
    articles = news.get("articles", [])  # type: ignore
    if not articles:
        return []
    processed_articles = []
    for article in articles:
        processed_article = {
            "title": article.get("title", ""),
            "author": article.get("author"),
            "link": article.get("link"),
            "description": article.get("description"),
            "content": article.get("content"),
            "query": query,
            "project_id": project_id,
        }
        processed_articles.append(processed_article)
    result = news_collection.insert_many(processed_articles)
    project_collection.update_one(
        {"_id": project_id}, {"$set": {"fetchState.news": True}}
    )
    inserted_articles = list(
        news_collection.find({"_id": {"$in": result.inserted_ids}})
    )
    return inserted_articles


@app.get("/get-tweets", response_model=list[TwitterModel])
async def get_tweets(
    project_id: str, query: str, count: int = 10
) -> list[TwitterModel]:
    existing_tweets = list(
        tweets_collection.find({"query": query, "project_id": project_id})
    )
    if existing_tweets:
        project_collection.update_one(
            {"_id": project_id}, {"$set": {"fetchState.socialMedia": True}}
        )
        return existing_tweets
    tweets = await asyncio.to_thread(scrap_twitter_x, query, count=count)
    if not tweets:
        return []
    processed_tweets = []
    for tweet in tweets:
        processed_tweet = {
            "tweet_id": tweet.get("id", ""),
            "url": tweet.get("url"),
            "text": tweet.get("text", ""),
            "retweet_count": tweet.get("retweet_count", 0),
            "reply_count": tweet.get("reply_count", 0),
            "like_count": tweet.get("like_count", 0),
            "quote_count": tweet.get("quote_count", 0),
            "created_at": tweet.get("created_at"),
            "lang": tweet.get("lang"),
            "author": tweet.get("author", {}),
            "entities": tweet.get("entities", {}),
            "query": query,
            "project_id": project_id,
        }
        processed_tweets.append(processed_tweet)
    result = tweets_collection.insert_many(processed_tweets)
    project_collection.update_one(
        {"_id": project_id}, {"$set": {"fetchState.socialMedia": True}}
    )
    inserted_tweets = list(
        tweets_collection.find({"_id": {"$in": result.inserted_ids}})
    )
    return inserted_tweets


@app.get("/clean-app-review")
def clean_app_review(review_id: str) -> str | None:
    review = reviews_collection.find_one({"_id": ObjectId(review_id)})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    cleaned_review = clean_review(review["review"])
    return cleaned_review


@app.get("/clean-news")
def clean_news(news_id: str) -> str:
    news = news_collection.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    cleaned_news = clean_news_content(news["content"])
    return cleaned_news


@app.get("/clean-tweet")
def clean_tweet(tweet_id: str) -> str:
    tweet = tweets_collection.find_one({"_id": ObjectId(tweet_id)})
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet not found")
    cleaned_tweet = clean_tweet_text(tweet["text"])
    return cleaned_tweet


@app.post("/extract-user-story", response_model=list[StoryOut])
def extract_user_story(req: ExtractRequest):
    try:
        models = extract_user_stories(
            source=req.source,
            source_id=req.source_id,
            content=req.content,
            min_similarity=req.min_similarity,
            dedupe=req.dedupe,
        )
        return [_to_story_out(m) for m in models]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")
