from config import settings
import httpx
from fastapi import HTTPException
from typing import Dict, Any
import json

INSIGHT_WEBHOOK_URL = settings.insight_generator_webhook


async def generate_insight_for_story(story: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calls the AI insight generator webhook with a single user story.
    Returns a dictionary representing the generated insight.
    """
    if not INSIGHT_WEBHOOK_URL:
        raise HTTPException(
            status_code=500, detail="Insight generator webhook URL is not configured."
        )

    try:
        async with httpx.AsyncClient() as client:
            # Mengirim satu cerita dalam payload, bukan daftar
            resp = await client.post(
                INSIGHT_WEBHOOK_URL,
                json={"story": story},
                headers={"Content-Type": "application/json"},
                timeout=120.0,
            )

        if not resp.is_success:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Failed to get response from Insight AI service: {resp.text}",
            )
        try:
            data = resp.json()
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500,
                detail=f"Insight AI service returned an invalid JSON response. Response text: '{resp.text}'",
            )

        # The service may return the insight directly or wrapped under 'output'
        if isinstance(data, dict) and "output" in data:
            return data["output"]

        return data

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to Insight AI service: {exc}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
