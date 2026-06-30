import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.services.user_service import UserService

router = APIRouter(tags=["users"])


class ProfileResponse(BaseModel):
    user_id: str
    profile: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    profile: dict


class AddMemoryRequest(BaseModel):
    type: str = "fact"
    content: str
    importance: float = 0.5
    source_msg_id: uuid.UUID | None = None


class MemoryFragmentResponse(BaseModel):
    fragment_id: uuid.UUID
    type: str
    content: str
    importance: float
    score: float | None = None
    created_at: datetime


def _service(db: AsyncSession) -> UserService:
    return UserService(db)


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


@router.get("/users/{user_id}/profile", response_model=ProfileResponse)
async def get_profile(user_id: str, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    user = await svc.get_user(user_id)
    if not user:
        raise _not_found("User")
    return user


@router.patch("/users/{user_id}/profile", response_model=ProfileResponse)
async def update_profile(
    user_id: str, body: ProfileUpdate, db: AsyncSession = Depends(get_db)
):
    svc = _service(db)
    user = await svc.update_profile(user_id, body.profile)
    if not user:
        raise _not_found("User")
    return user


@router.post(
    "/users/{user_id}/memories",
    response_model=MemoryFragmentResponse,
    status_code=201,
)
async def add_memory(
    user_id: str, body: AddMemoryRequest, db: AsyncSession = Depends(get_db)
):
    svc = _service(db)
    await svc.get_or_create_user(user_id)
    fragment = await svc.add_memory_fragment(
        user_id=user_id,
        type=body.type,
        content=body.content,
        importance=body.importance,
        source_msg_id=body.source_msg_id,
    )
    return MemoryFragmentResponse(
        fragment_id=fragment.fragment_id,
        type=fragment.type,
        content=fragment.content,
        importance=fragment.importance,
        created_at=fragment.created_at,
    )


@router.get("/users/{user_id}/memories", response_model=list[MemoryFragmentResponse])
async def search_memories(
    user_id: str,
    query: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=100),
    type: str | None = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db),
):
    svc = _service(db)
    if not await svc.get_user(user_id):
        raise _not_found("User")

    results = await svc.search_memories(
        user_id=user_id,
        query=query,
        top_k=top_k,
        fragment_type=type,
    )
    return [
        MemoryFragmentResponse(
            fragment_id=frag.fragment_id,
            type=frag.type,
            content=frag.content,
            importance=frag.importance,
            score=score,
            created_at=frag.created_at,
        )
        for frag, score in results
    ]


@router.delete("/users/{user_id}/memories/{fragment_id}", status_code=204)
async def delete_memory(
    user_id: str, fragment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    svc = _service(db)
    if not await svc.get_user(user_id):
        raise _not_found("User")

    deleted = await svc.delete_memory_fragment(fragment_id)
    if not deleted:
        raise _not_found("Memory fragment")
