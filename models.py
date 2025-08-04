from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from typing import Optional
from typing_extensions import Annotated
from pydantic.functional_validators import BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(str)]


class CaseStudyRequest(BaseModel):
    case_study: str


class UpdateQueriesRequest(BaseModel):
    session_id: str
    queries: list[str]


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
