import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.services.llm_service import LLMService
from src.services.session_service import SessionService

router = APIRouter(tags=["sessions"])


# ============================================================
# Pydantic Schemas
# ============================================================


class SessionCreate(BaseModel):
    agent_id: str
    user_id: str
    session_id: str | None = None


class SessionUpdate(BaseModel):
    status: str | None = None
    agent_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    agent_id: str | None = None
    user_id: str
    status: str
    message_count: int
    summary: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    role: str
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None


class MessageResponse(BaseModel):
    message_id: uuid.UUID
    session_id: str
    role: str
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Endpoints
# ============================================================


def _service(db: AsyncSession) -> SessionService:
    return SessionService(db)


@router.post("/sessions", response_model=SessionResponse)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    try:
        session = await svc.create_session(
            agent_id=body.agent_id,
            user_id=body.user_id,
            session_id=body.session_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail=f"Session '{body.session_id}' already exists",
        )
    return session


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, body: SessionUpdate, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    session = await svc.update_session(session_id, body.status, body.agent_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    deleted = await svc.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def add_message(
    session_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    svc = _service(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    message = await svc.add_message(
        session_id=session_id,
        role=body.role,
        content=body.content,
        tool_name=body.tool_name,
        tool_call_id=body.tool_call_id,
    )
    background_tasks.add_task(
        LLMService.run_post_message,
        session_id=session_id,
        message_id=message.message_id,
        content=body.content,
        agent_id=session.agent_id,
        user_id=session.user_id,
    )
    return message


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await svc.get_messages(session_id, limit=limit)
    return messages
