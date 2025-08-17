from config import settings

WEBHOOK_URL = settings.ai_userstory_generator_webhook

from typing import List, Dict, Any
import httpx
from fastapi import HTTPException
from config import settings

WEBHOOK_URL = settings.ai_userstory_generator_webhook

# Expected keys per user story item
_REQUIRED_KEYS = {
    "who",
    "what",
    "why",
    "as_a_i_want_so_that",
    "evidence",
    "sentiment",
    "confidence",
    "field_insight",
}


async def generate_userstory_with_ai(
    content_type: str, content: str
) -> List[Dict[str, Any]]:
    """
    Calls the AI user story generator webhook.

    message = "<content_type>\\n<content>"

    Returns a list of user story dicts with keys:
    who, what, why, as_a_i_want_so_that, evidence, sentiment, confidence
    """
    message = f"{content_type}\n{content}".strip()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                WEBHOOK_URL,
                json={"message": message},
                headers={"Content-Type": "application/json"},
                timeout=120.0,
            )

        if not resp.is_success:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Failed to get response from AI service",
            )

        data = resp.json()

        # Service may return directly a list OR wrap under 'output'
        if isinstance(data, dict):
            if "output" in data:
                payload = data["output"]
            else:
                # Maybe nested like {"output": {"userStories": [...]}}
                if "userStories" in data:
                    payload = data["userStories"]
                else:
                    # If dict doesn't contain expected keys, error
                    raise HTTPException(
                        status_code=500,
                        detail="Unexpected response format (dict without 'output')",
                    )
        else:
            payload = data

        # Unwrap if still wrapped
        if isinstance(payload, dict) and "userStories" in payload:
            payload = payload["userStories"]

        if not isinstance(payload, list):
            raise HTTPException(
                status_code=500,
                detail="AI service output is not a list",
            )

        cleaned: List[Dict[str, Any]] = []
        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            missing = _REQUIRED_KEYS - item.keys()
            if missing:
                # Skip incomplete entries
                continue
            # Type coercions / safety
            item["who"] = str(item["who"])
            item["what"] = str(item["what"])
            item["why"] = str(item["why"])
            item["as_a_i_want_so_that"] = str(item["as_a_i_want_so_that"])
            item["evidence"] = str(item["evidence"])
            item["sentiment"] = str(item["sentiment"])
            try:
                item["confidence"] = float(item["confidence"])
            except Exception:
                item["confidence"] = 0.0

            if "field_insight" in item and not isinstance(item["field_insight"], dict):
                item["field_insight"] = None
            cleaned.append(item)

        return cleaned

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to AI user story service: {exc}",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
