import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.database import Skill
from src.services.agent_service import AgentService

router = APIRouter(tags=["agents"])


# ============================================================
# Pydantic Schemas
# ============================================================


class AgentCreate(BaseModel):
    agent_id: str
    name: str
    persona: str = ""
    config: dict = {}


class AgentUpdate(BaseModel):
    name: str | None = None
    persona: str | None = None
    config: dict | None = None
    status: str | None = None


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    persona: str
    config: dict
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentSkillResponse(BaseModel):
    skill_id: uuid.UUID
    name: str
    trigger_keys: list[str]
    prompt_snippet: str
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillBindingResponse(BaseModel):
    skill_id: uuid.UUID
    agent_id: str
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Helpers
# ============================================================


def _service(db: AsyncSession) -> AgentService:
    return AgentService(db)


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


def _already_exists(entity: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"{entity} already exists")


# ============================================================
# Endpoints
# ============================================================


@router.post("/agents", response_model=AgentResponse)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    existing = await svc.get_agent(body.agent_id)
    if existing:
        raise _already_exists("Agent")
    return await svc.create_agent(
        agent_id=body.agent_id,
        name=body.name,
        persona=body.persona,
        config=body.config,
    )


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    agent = await svc.get_agent(agent_id)
    if not agent:
        raise _not_found("Agent")
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    agent = await svc.update_agent(
        agent_id,
        name=body.name,
        persona=body.persona,
        config=body.config,
        status=body.status,
    )
    if not agent:
        raise _not_found("Agent")
    return agent


@router.post("/agents/{agent_id}/skills/{skill_id}", response_model=SkillBindingResponse, status_code=201)
async def add_skill_to_agent(
    agent_id: str, skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    svc = _service(db)
    try:
        return await svc.add_skill_to_agent(agent_id, skill_id)
    except ValueError as e:
        msg = str(e)
        if "already bound" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=404, detail=msg)


@router.delete("/agents/{agent_id}/skills/{skill_id}", status_code=204)
async def remove_skill_from_agent(
    agent_id: str, skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    svc = _service(db)
    removed = await svc.remove_skill_from_agent(agent_id, skill_id)
    if not removed:
        raise _not_found("Skill binding")


@router.get("/agents/{agent_id}/skills", response_model=list[AgentSkillResponse])
async def get_agent_skills(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = _service(db)
    if not await svc.get_agent(agent_id):
        raise _not_found("Agent")

    bindings = await svc.get_agent_skill_bindings(agent_id)
    results = []
    for b in bindings:
        skill = await db.get(Skill, b.skill_id)
        if skill:
            results.append(
                AgentSkillResponse(
                    skill_id=skill.skill_id,
                    name=skill.name,
                    trigger_keys=skill.trigger_keys,
                    prompt_snippet=skill.prompt_snippet,
                    enabled=b.enabled,
                    created_at=b.created_at,
                )
            )
    return results
