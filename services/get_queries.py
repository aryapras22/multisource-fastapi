import httpx
from fastapi import HTTPException
from config import settings


async def generate_queries_from_case_study(case_study: str) -> list:

    try:

        webhook_url = settings.queries_generator_webhook

        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json={"message": case_study},
                headers={"Content-Type": "application/json"},
                timeout=60.0,
            )

            if not response.is_success:
                error_data = response.text
                print(f"Error from service: {error_data}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to get response from service",
                )

            data = response.json()
            reply = data.get("output")

            if reply is None:
                raise HTTPException(
                    status_code=500,
                    detail="Workflow response is missing 'output' field",
                )
            return reply.get("queries")

    except httpx.RequestError as exc:
        print(f"An error occurred while requesting {exc.request.url}.")
        raise HTTPException(
            status_code=503, detail="Could not connect to the generate queries service"
        )
    except Exception as error:
        print(f"API Route Error: {error}")
        raise HTTPException(status_code=500, detail="An internal server error occurred")
