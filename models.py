from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from typing import Literal, Optional
from datetime import datetime
from typing_extensions import Annotated
from pydantic.functional_validators import BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(str)]


class CaseStudyRequest(BaseModel):
    name: str
    case_study: str


class UpdateQueriesRequest(BaseModel):
    session_id: str
    queries: list[str]


class ProjectDataSources(BaseModel):
    appStores: bool = True
    news: bool = True
    socialMedia: bool = True


class ProjectModel(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    case_study: str
    description: Optional[str] = None
    created_at: datetime
    status: Literal["draft", "configured", "analyzing", "complete"] = "draft"
    queries: Optional[list[str]] = None
    dataSources: ProjectDataSources = Field(default_factory=ProjectDataSources)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class CreateProjectRequest(BaseModel):
    name: str
    case_study: str
    description: Optional[str] = None
    dataSources: Optional[ProjectDataSources] = None


class UpdateProjectConfigRequest(BaseModel):
    id: str
    queries: Optional[list[str]] = None
    dataSources: Optional[ProjectDataSources] = None
    description: Optional[str] = None


class AppModel(BaseModel):
    # Map the 'id' field to MongoDB's '_id' and handle conversion
    id: PyObjectId = Field(alias="_id")

    appName: str
    appId: str | int
    developer: str
    ratingScore: Optional[float] = None
    app_desc: Optional[str] = None
    icon: HttpUrl
    url: Optional[str] = None
    store: str
    session_id: str

    model_config = ConfigDict(
        # This allows Pydantic to populate the model using the field alias '_id'
        populate_by_name=True,
        # This is needed to allow the custom PyObjectId type
        arbitrary_types_allowed=True,
    )


class ReviewModel(BaseModel):
    # Map the 'id' field to MongoDB's '_id' and handle conversion
    id: PyObjectId = Field(alias="_id")

    reviewer: str
    rating: int | float
    review: str
    app_id: str | int
    store: str
    session_id: str

    model_config = ConfigDict(
        # This allows Pydantic to populate the model using the field alias '_id'
        populate_by_name=True,
        # This is needed to allow the custom PyObjectId type
        arbitrary_types_allowed=True,
    )


class NewsModel(BaseModel):
    # Map the 'id' field to MongoDB's '_id' and handle conversion
    id: PyObjectId = Field(alias="_id")

    title: str
    author: Optional[str] = None
    link: Optional[HttpUrl] = None
    description: Optional[str] = None
    content: Optional[str] = None
    query: str
    session_id: str

    model_config = ConfigDict(
        # This allows Pydantic to populate the model using the field alias '_id'
        populate_by_name=True,
        # This is needed to allow the custom PyObjectId type
        arbitrary_types_allowed=True,
    )


class TwitterModel(BaseModel):
    # Map the 'id' field to MongoDB's '_id' and handle conversion
    id: PyObjectId = Field(alias="_id")

    tweet_id: str
    url: Optional[str] = None
    text: str
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    created_at: Optional[str] = None
    lang: Optional[str] = None
    author: dict
    entities: dict = {}
    query: str
    session_id: str

    model_config = ConfigDict(
        # This allows Pydantic to populate the model using the field alias '_id'
        populate_by_name=True,
        # This is needed to allow the custom PyObjectId type
        arbitrary_types_allowed=True,
    )
