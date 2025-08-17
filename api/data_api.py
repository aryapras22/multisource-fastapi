import asyncio
from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError
from bson.objectid import ObjectId

from db import (
    project_collection,
    apps_collection,
    reviews_collection,
    news_collection,
    tweets_collection,
)
from models import AppModel, NewsModel, ReviewModel, TwitterModel
from services.app_scrapper import (
    get_appstore_apps,
    get_appstore_reviews,
    get_google_play_apps,
    get_google_play_reviews,
)
from services.news_scrapper import scrap_news
from services.preprocessing import clean_news_content, clean_review, clean_tweet_text
from services.twitter_x_scrapper import scrap_twitter_x

router = APIRouter()


@router.get("/get-project-apps", response_model=list[AppModel])
def get_project_apps(project_id: str) -> list:
    doc = apps_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Apps not found")
    return list(doc)


@router.get("/get-project-app-reviews", response_model=list[ReviewModel])
def get_project_app_reviews(project_id: str) -> list:
    doc = reviews_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Reviews not found")
    return list(doc)


@router.get("/get-project-news", response_model=list[NewsModel])
def get_project_news(project_id: str) -> list:
    doc = news_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="News not found")
    return list(doc)


@router.get("/get-project-tweets", response_model=list[TwitterModel])
def get_project_tweets(project_id: str) -> list:
    doc = tweets_collection.find({"project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Tweets not found")
    return list(doc)


@router.get("/get-apps", response_model=list[AppModel])
async def get_apps(project_id: str, limit: int = 10) -> list:
    case_study_data = project_collection.find_one({"_id": project_id})
    if not case_study_data:
        raise HTTPException(status_code=404, detail="Project ID not found")
    apps_list = list(apps_collection.find({"project_id": project_id}))
    if apps_list:
        if not case_study_data.get("fetchState", {}).get("appStores"):
            project_collection.update_one(
                {"_id": project_id}, {"$set": {"fetchState.appStores": True}}
            )
        return apps_list
    queries = case_study_data.get("queries", [])
    tasks = [
        asyncio.to_thread(get_google_play_apps, query, limit=limit) for query in queries
    ]
    tasks.extend(
        [asyncio.to_thread(get_appstore_apps, query, limit=limit) for query in queries]
    )
    results = await asyncio.gather(*tasks)
    all_apps = []
    for i, query_apps in enumerate(results):
        store = "google" if i < len(queries) else "apple"
        for app in query_apps:
            app["store"] = store
            app["project_id"] = project_id
            all_apps.append(app)
    unique_apps_dict = {(app["appId"], app["store"]): app for app in all_apps}
    unique_apps_list = list(unique_apps_dict.values())
    if unique_apps_list:
        try:
            apps_collection.insert_many(unique_apps_list)
        except DuplicateKeyError:
            pass  # Ignore duplicates if scraping is re-run
        project_collection.update_one(
            {"_id": project_id}, {"$set": {"fetchState.appStores": True}}
        )
    return list(apps_collection.find({"project_id": project_id}))


@router.get("/get-reviews", response_model=list[ReviewModel])
async def get_reviews(
    project_id: str,
    store: str,
    app_id: str,
    count: int = 10,
) -> list[ReviewModel]:
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


@router.get("/get-news", response_model=list[NewsModel])
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
    articles = news.get("articles", []) if isinstance(news, dict) else news
    if not articles:
        return []
    processed_articles = [
        {
            "title": article.get("title", ""),
            "author": article.get("author"),
            "link": article.get("link"),
            "description": article.get("description"),
            "content": article.get("content"),
            "query": query,
            "project_id": project_id,
        }
        for article in articles
    ]
    if processed_articles:
        result = news_collection.insert_many(processed_articles)
        project_collection.update_one(
            {"_id": project_id}, {"$set": {"fetchState.news": True}}
        )
        return list(news_collection.find({"_id": {"$in": result.inserted_ids}}))
    return []


@router.get("/get-tweets", response_model=list[TwitterModel])
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
    processed_tweets = [
        {
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
        for tweet in tweets
    ]
    if processed_tweets:
        result = tweets_collection.insert_many(processed_tweets)
        project_collection.update_one(
            {"_id": project_id}, {"$set": {"fetchState.socialMedia": True}}
        )
        return list(tweets_collection.find({"_id": {"$in": result.inserted_ids}}))
    return []


@router.get("/clean-app-review")
def clean_app_review(review_id: str) -> str | None:
    review = reviews_collection.find_one({"_id": ObjectId(review_id)})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return clean_review(review["review"])


@router.get("/clean-news")
def clean_news(news_id: str) -> str:
    news = news_collection.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    return clean_news_content(news["content"])


@router.get("/clean-tweet")
def clean_tweet(tweet_id: str) -> str:
    tweet = tweets_collection.find_one({"_id": ObjectId(tweet_id)})
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet not found")
    return clean_tweet_text(tweet["text"])
