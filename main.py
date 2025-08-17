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
    UpdateFetchStateRequest,
    UpdateProjectConfigRequest,
    ProjectFetchState,
    _to_story_out,
    StoryWithSourceOut,
    SourceInfo,
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
    user_stories_collection,
)
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument
from services.preprocessing import clean_news_content, clean_review, clean_tweet_text
from services.twitter_x_scrapper import scrap_twitter_x
from bson.objectid import ObjectId
from services.user_story_extractor import extract_user_stories
from api.usecase_api import router as usecase_router
from api.ai_userstories_api import router as ai_userstories_router
from api.clustering_api import router as clustering_router
from api.projects_api import router as projects_router
from api.data_api import router as data_router
from api.user_stories_api import router as user_stories_router
from api.insight_generator_api import router as insight_generator

app = FastAPI()


app.include_router(projects_router, tags=["Projects"])
app.include_router(data_router, tags=["Data"])
app.include_router(user_stories_router, tags=["User Stories Generator"])
app.include_router(clustering_router)
app.include_router(insight_generator, tags=["Insight Generator"])
app.include_router(usecase_router, tags=["Usecase Generator"])
app.include_router(ai_userstories_router, tags=["AI User Stories Generator"])


origins = [settings.frontend_origin, "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
