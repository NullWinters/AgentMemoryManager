from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.services.context_service import ContextService

router = APIRouter(tags=["context"])


# ============================================================
# Pydantic Schemas
# ============================================================


class ContextOptions(BaseModel):
    max_session_turns: int = 20
    user_memory_top_k: int = 5
    include_skills: bool = True
    include_profile: bool = True
    query_embedding: list[float] | None = None


class ContextRequest(BaseModel):
    agent_id: str
    user_id: str
    session_id: str
    query: str | None = None
    options: ContextOptions | None = None


class AgentMemoryResponse(BaseModel):
    agent_id: str
    persona: str | None = None
    skills: list[dict] = []


class UserMemoryResponse(BaseModel):
    profile: dict = {}
    fragments: list[dict] = []


class SessionMemoryResponse(BaseModel):
    session_id: str
    message_count: int = 0
    summary: str | None = None
    messages: list[dict] = []


class ContextResponse(BaseModel):
    agent_memory: AgentMemoryResponse
    user_memory: UserMemoryResponse
    session_memory: SessionMemoryResponse


# ============================================================
# Endpoint
# ============================================================


@router.post("/context", response_model=ContextResponse)
async def compose_context(body: ContextRequest, db: AsyncSession = Depends(get_db)):
    svc = ContextService(db)
    opts = body.options
    top_k = opts.user_memory_top_k if opts else 5
    query_embedding = opts.query_embedding if opts else None
    context = await svc.compose_context(
        agent_id=body.agent_id,
        user_id=body.user_id,
        session_id=body.session_id,
        query=body.query,
        top_k=top_k,
        query_embedding=query_embedding,
    )
    return context
