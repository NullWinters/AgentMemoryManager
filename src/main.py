import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from src.config import MEMORY_API_KEY
from src.routers import admin, agents, context, sessions, skills

API_KEY_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Agent Memory Manager", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key middleware
if MEMORY_API_KEY:

    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next):
        if request.url.path.startswith(API_KEY_PREFIX):
            key = request.headers.get("X-API-Key") or (
                request.headers.get("Authorization", "").removeprefix("Bearer ")
            )
            if key != MEMORY_API_KEY:
                return JSONResponse(
                    status_code=401, content={"detail": "Invalid or missing API key"}
                )
        return await call_next(request)


# Routers
app.include_router(agents.router, prefix=API_KEY_PREFIX)
app.include_router(skills.router, prefix=API_KEY_PREFIX)
app.include_router(sessions.router, prefix=API_KEY_PREFIX)
app.include_router(context.router, prefix=API_KEY_PREFIX)
app.include_router(admin.router, prefix=API_KEY_PREFIX)

# Debug console — served at /debug
static_dir = os.path.join(os.path.dirname(__file__), "static")


@app.get("/debug", include_in_schema=False)
async def debug_console():
    return FileResponse(os.path.join(static_dir, "debug.html"))
