from __future__ import annotations
from fastapi import APIRouter, HTTPException

from db import use_cases_collection  # your Mongo collection
from models import GenerateUseCaseRequest, UseCaseDiagramResponse
from services.usecase_diagram_service import create_use_case_diagrams_by_project

router = APIRouter(prefix="/usecases", tags=["usecases"])


@router.post("/diagram", response_model=UseCaseDiagramResponse)
def generate_usecase_diagram(req: GenerateUseCaseRequest):
    try:
        result = create_use_case_diagrams_by_project(req.project_id)
        return UseCaseDiagramResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate diagram: {e}")


@router.get("/diagram/{project_id}", response_model=UseCaseDiagramResponse)
def get_latest_usecase_diagram(project_id: str):
    """
    Return the most recent stored diagram for this project_id.
    (Assumes you inserted snapshots. If you used an upsert-one design,
     just find_one by project_id.)
    """
    try:
        doc = (
            use_cases_collection.find({"project_id": project_id})
            .sort("generated_at", -1)
            .limit(1)
        )
        docs = list(doc)
        if not docs:
            raise HTTPException(
                status_code=404, detail="No diagram found for project_id"
            )

        latest = docs[0]
        # Convert Mongo doc to response
        return UseCaseDiagramResponse(
            project_id=latest["project_id"],
            diagrams_puml=latest.get("diagrams_puml", []),
            diagrams_url=latest.get("diagrams_url", []),
            stats=latest.get("stats", {}),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load diagram: {e}")
