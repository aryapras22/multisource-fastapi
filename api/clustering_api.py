from __future__ import annotations

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


from models import UserStoryModel
from services.clustering_service import cluster_and_summarize_stories  # Assuming UserStoryModel is in a shared models file

router = APIRouter(prefix="/clustering", tags=["clustering"])


# --- Pydantic Models for API Response ---


class Cluster(BaseModel):
    cluster_id: int
    representative_story: UserStoryModel
    stories: List[UserStoryModel]
    size: int
    sources: List[str]


class ClusteringResponse(BaseModel):
    project_id: str
    clusters: List[Cluster]


# --- API Endpoint ---


@router.get("/user_stories/{project_id}", response_model=ClusteringResponse)
def get_clustered_user_stories(
    project_id: str,
    distance: float = Query(
        0.5,
        ge=0,
        le=1.0,
        title="Distance Threshold",
        description="Similarity distance for clustering (lower means more similar).",
    ),
):
    """
    Analyzes all user stories for a given project and groups them into clusters
    of semantically similar stories.

    - **Intra-source similarity**: Indicated when a cluster contains stories from a single source.
    - **Inter-source similarity**: Indicated when a cluster contains stories from multiple sources.
    - **Most Occurring Story**: Each cluster has a `representative_story` which is the
      most central and representative member of that group.
    """
    try:
        result = cluster_and_summarize_stories(
            project_id=project_id, distance_threshold=distance
        )
        return ClusteringResponse(**result)
    except Exception as e:
        # Log the exception e for debugging
        raise HTTPException(
            status_code=500, detail=f"Failed to process and cluster stories: {e}"
        )
