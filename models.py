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
    # renamed
    project_id: str
    queries: list[str]


class ProjectFetchState(BaseModel):
    appStores: bool = False
    news: bool = False
    socialMedia: bool = False
    reviews: bool = False
    userStories: bool = False
    useCase: bool = False
    aiUserStories: Optional[bool] = None
    aiUseCase: Optional[bool] = None


class UpdateFetchStateRequest(BaseModel):
    project_id: str
    appStores: Optional[bool] = None
    news: Optional[bool] = None
    socialMedia: Optional[bool] = None
    reviews: Optional[bool] = None
    userStories: Optional[bool] = None
    useCase: Optional[bool] = None
    aiUserStories: Optional[bool] = None
    aiUseCase: Optional[bool] = None


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
    fetchState: ProjectFetchState = Field(default_factory=ProjectFetchState)

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


class UpdateProjectStatusRequest(BaseModel):
    project_id: str
    status: Literal["draft", "configured", "analyzing", "complete"]


class AppModel(BaseModel):
    id: PyObjectId = Field(alias="_id")
    appName: str
    appId: str | int
    developer: str
    ratingScore: Optional[float] = None
    app_desc: Optional[str] = None
    icon: HttpUrl
    url: Optional[str] = None
    store: str
    project_id: str  # renamed

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class ReviewModel(BaseModel):
    id: PyObjectId = Field(alias="_id")
    reviewer: str
    rating: int | float
    review: str
    app_id: str | int
    store: str
    project_id: str  # renamed

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class NewsModel(BaseModel):
    id: PyObjectId = Field(alias="_id")
    title: str
    author: Optional[str] = None
    link: Optional[HttpUrl] = None
    description: Optional[str] = None
    content: Optional[str] = None
    query: str
    project_id: str  # renamed

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class TwitterModel(BaseModel):
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
    project_id: str  # renamed

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


SourceType = Literal["review", "news", "tweet"]


class UserStoryModel(BaseModel):
    id: PyObjectId = Field(alias="_id")
    who: str
    what: str
    why: Optional[str]
    full_sentence: Optional[str] = None
    similarity_score: float
    source: SourceType
    source_id: str
    project_id: str
    insight: Optional[Insight] = None  # Ditambahkan

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class Insight(BaseModel):
    nfr: list[str]
    business_impact: str
    pain_point_jtbd: str
    fit_score: FitScore


class FitScore(BaseModel):
    score: float
    explanation: str


class ExtractRequest(BaseModel):
    source: SourceType
    source_id: str
    content: str
    project_id: str  # added
    min_similarity: float = 0.70
    dedupe: bool = True


class StoryOut(BaseModel):
    id: str = Field(alias="_id")
    who: str
    what: str
    why: Optional[str] = None
    full_sentence: Optional[str] = None
    similarity_score: float
    source: SourceType
    source_id: str
    project_id: str
    insight: Optional[Insight] = None
    model_config = ConfigDict(populate_by_name=True)


def _to_story_out(m: UserStoryModel) -> StoryOut:
    return StoryOut(
        _id=str(m.id),
        who=m.who,
        what=m.what,
        why=m.why,
        full_sentence=m.full_sentence,
        similarity_score=m.similarity_score,
        source=m.source,
        source_id=m.source_id,
        project_id=m.project_id,
        insight=m.insight,  # Ditambahkan
    )


class SourceInfo(BaseModel):
    type: Literal["news", "review", "tweet"]  # changed from tweets -> tweet
    title: str
    author: Optional[str] = None
    content: str
    link: Optional[str] = None
    rating: Optional[float] = None


class StoryWithSourceOut(StoryOut):
    source_data: SourceInfo


class UseCaseDiagramDoc(BaseModel):
    id: PyObjectId = Field(alias="_id")
    project_id: str
    diagrams_puml: list[str]
    diagrams_url: list[str]
    stats: dict
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class GenerateUseCaseRequest(BaseModel):
    project_id: str


class UseCaseDiagramResponse(BaseModel):
    project_id: str
    diagrams_puml: list[str]
    diagrams_url: list[str]
    stats: dict


class FieldInsight(BaseModel):
    nfr: list[str]
    business_impact: str
    pain_point_jtbd: str


class AIUserStoryItem(BaseModel):
    who: str
    what: str
    why: Optional[str] = None
    as_a_i_want_so_that: str
    evidence: str
    sentiment: str
    confidence: float
    content_id: Optional[str] = None
    field_insight: Optional[FieldInsight] = None


class GenerateAIUserStoriesRequest(BaseModel):
    content_type: Literal["review", "news", "tweet", "mixed", "raw"]
    content: str
    project_id: Optional[str] = None
    persist: bool = False
    content_id: Optional[str] = None


class GenerateAIUserStoriesResponse(BaseModel):
    project_id: Optional[str] = None
    content_id: Optional[str] = None
    count: int
    stories: list[AIUserStoryItem]


class AIUserStoryDocOut(AIUserStoryItem):
    id: str = Field(alias="_id")
    project_id: Optional[str] = None
    content_type: Optional[str] = None
    created_at: Optional[datetime] = None
