from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from api.usecase_api import router as usecase_router
from api.ai_userstories_api import router as ai_userstories_router
from api.clustering_api import router as clustering_router
from api.projects_api import router as projects_router
from api.data_api import router as data_router
from api.user_stories_api import router as user_stories_router
from api.insight_generator_api import router as insight_generator
from api.analytics_api import router as analytics_router

app = FastAPI()

# Setup CORS middleware FIRST
origins = [settings.frontend_origin, "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key validation middleware
@app.middleware("http")
async def validate_api_key(request: Request, call_next):
    from fastapi.responses import JSONResponse
    
    # Skip validation for CORS preflight (OPTIONS) and docs endpoints
    if request.method == "OPTIONS" or request.url.path in ["/", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)
    
    # Get API key from query parameter (Cloudflare blocks custom headers)
    api_key = request.query_params.get("key")
    
    print(f"[DEBUG] Method: {request.method}")
    print(f"[DEBUG] Query Params: {dict(request.query_params)}")
    print(f"[DEBUG] Received API Key: {api_key}")
    print(f"[DEBUG] Expected API Key: {settings.api_key}")
    print(f"[DEBUG] Path: {request.url.path}")
    
    if not settings.api_key:
        return JSONResponse(
            status_code=500,
            content={"detail": "API key not configured on server"},
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
            }
        )
    
    if api_key != settings.api_key:
        return JSONResponse(
            status_code=403,
            content={"detail": "Invalid or missing API key"},
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
            }
        )
    
    response = await call_next(request)
    return response

# Include routers (no dependencies needed, middleware handles auth)
app.include_router(projects_router, tags=["Projects"])
app.include_router(data_router, tags=["Data"])
app.include_router(user_stories_router, tags=["User Stories Generator"])
app.include_router(clustering_router)
app.include_router(insight_generator, tags=["Insight Generator"])
app.include_router(usecase_router, tags=["Usecase Generator"])
app.include_router(ai_userstories_router, tags=["AI User Stories Generator"])
app.include_router(analytics_router, tags=["Analytics"])
