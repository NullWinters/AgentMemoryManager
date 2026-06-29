from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.routers import agents, sessions, skills


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Agent Memory Manager", version="1.0.0", lifespan=lifespan)

app.include_router(agents.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
