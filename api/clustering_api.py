from __future__ import annotations

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


from models import AIClusteringResponse, UserStoryModel
from services.clustering_service import (
    cluster_and_summarize_ai_stories,
    cluster_and_summarize_stories,
    create_usecase_diagram_from_cluster,
    create_usecase_diagram_from_ai_cluster,
    cluster_and_generate_usecases,
    cluster_and_generate_ai_usecases,
)  # Assuming UserStoryModel is in a shared models file

router = APIRouter(prefix="/clustering", tags=["clustering"])


class Cluster(BaseModel):
    cluster_id: int
    representative_story: UserStoryModel
    stories: List[UserStoryModel]
    size: int
    sources: List[str]


class ClusteringResponse(BaseModel):
    project_id: str
    clusters: List[Cluster]


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


@router.get("/ai_user_stories/{project_id}", response_model=AIClusteringResponse)
def get_clustered_ai_user_stories(
    project_id: str,
    distance: float = Query(
        0.5,
        ge=0,
        le=1.0,
        title="Distance Threshold",
        description="Similarity distance for clustering (lower means more similar).",
    ),
):
    try:
        result = cluster_and_summarize_ai_stories(
            project_id=project_id, distance_threshold=distance
        )
        return AIClusteringResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to process and cluster AI stories: {e}"
        )


@router.get("/user_stories/{project_id}/{cluster_id}/usecase")
def get_cluster_usecase_diagram(
    project_id: str,
    cluster_id: int,
    distance: float = Query(
        0.5,
        ge=0,
        le=1.0,
        title="Distance Threshold",
        description="Similarity distance for clustering (lower means more similar).",
    ),
):
    """
    Generate use case diagram for a specific cluster.
    The diagram includes the representative story and all stories in the cluster.
    """
    try:
        result = create_usecase_diagram_from_cluster(
            project_id=project_id, cluster_id=cluster_id, distance_threshold=distance
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate use case diagram: {e}"
        )


@router.get("/ai_user_stories/{project_id}/{cluster_id}/usecase")
def get_ai_cluster_usecase_diagram(
    project_id: str,
    cluster_id: int,
    distance: float = Query(
        0.5,
        ge=0,
        le=1.0,
        title="Distance Threshold",
        description="Similarity distance for clustering (lower means more similar).",
    ),
):
    """
    Generate use case diagram for a specific AI cluster.
    The diagram includes the representative story and all stories in the cluster.
    """
    try:
        result = create_usecase_diagram_from_ai_cluster(
            project_id=project_id, cluster_id=cluster_id, distance_threshold=distance
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate AI use case diagram: {e}"
        )


@router.get("/user_stories/{project_id}/with-usecases")
def get_clustered_user_stories_with_usecases(
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
    with ONE use case diagram containing the 10 representative stories.

    Returns clusters with their user stories AND a single unified use case diagram.
    Response includes:
    - project_id: Project identifier
    - clusters: Array of cluster objects with representative stories and all stories
    - usecase_diagram: Single PlantUML diagram containing all 10 representative stories
      - diagrams_puml: PlantUML source code
      - diagrams_url: URL to view the diagram
      - stats: Statistics about actors, use cases, edges, and clusters represented
    """
    try:
        result = cluster_and_generate_usecases(
            project_id=project_id, distance_threshold=distance
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process clusters with use cases: {e}",
        )


@router.get("/ai_user_stories/{project_id}/with-usecases")
def get_clustered_ai_user_stories_with_usecases(
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
    Analyzes all AI user stories for a given project and groups them into clusters
    with ONE use case diagram containing the 10 representative AI stories.

    Returns clusters with their AI stories AND a single unified use case diagram.
    Response includes:
    - project_id: Project identifier
    - clusters: Array of cluster objects with representative AI stories and all stories
    - usecase_diagram: Single PlantUML diagram containing all 10 representative AI stories
      - diagrams_puml: PlantUML source code
      - diagrams_url: URL to view the diagram
      - stats: Statistics about actors, use cases, edges, and clusters represented
    """
    try:
        result = cluster_and_generate_ai_usecases(
            project_id=project_id, distance_threshold=distance
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process AI clusters with use cases: {e}",
        )
