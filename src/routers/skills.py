import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.services.skill_service import SkillService

router = APIRouter(tags=["skills"])


# ============================================================
# Pydantic Schemas
# ============================================================


class SkillCreate(BaseModel):
    name: str
    trigger_keys: list[str]
    prompt_snippet: str = ""


class SkillUpdate(BaseModel):
    name: str | None = None
    trigger_keys: list[str] | None = None
    prompt_snippet: str | None = None


class SkillResponse(BaseModel):
    skill_id: uuid.UUID
    name: str
    trigger_keys: list[str]
    prompt_snippet: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Helpers
# ============================================================


def _service(db: AsyncSession) -> SkillService:
    return SkillService(db)


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


# ============================================================
# Endpoints
# ============================================================


@router.post("/skills", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreate, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    return await svc.create_skill(
        name=body.name,
        trigger_keys=body.trigger_keys,
        prompt_snippet=body.prompt_snippet,
    )


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    return await svc.list_skills()


@router.get("/skills/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    skill = await svc.get_skill(skill_id)
    if not skill:
        raise _not_found("Skill")
    return skill


@router.patch("/skills/{skill_id}", response_model=SkillResponse)
async def update_skill(skill_id: uuid.UUID, body: SkillUpdate, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    skill = await svc.update_skill(
        skill_id,
        name=body.name,
        trigger_keys=body.trigger_keys,
        prompt_snippet=body.prompt_snippet,
    )
    if not skill:
        raise _not_found("Skill")
    return skill


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    deleted = await svc.delete_skill(skill_id)
    if not deleted:
        raise _not_found("Skill")
