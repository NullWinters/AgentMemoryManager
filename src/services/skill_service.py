import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import Skill


class SkillService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_skill(
        self, name: str, trigger_keys: list[str], prompt_snippet: str = ""
    ) -> Skill:
        skill = Skill(name=name, trigger_keys=trigger_keys, prompt_snippet=prompt_snippet)
        self.db.add(skill)
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def list_skills(self) -> list[Skill]:
        result = await self.db.execute(select(Skill).order_by(Skill.created_at))
        return list(result.scalars().all())

    async def get_skill(self, skill_id: uuid.UUID) -> Skill | None:
        result = await self.db.execute(select(Skill).where(Skill.skill_id == skill_id))
        return result.scalar_one_or_none()

    async def update_skill(
        self,
        skill_id: uuid.UUID,
        name: str | None = None,
        trigger_keys: list[str] | None = None,
        prompt_snippet: str | None = None,
    ) -> Skill | None:
        skill = await self.get_skill(skill_id)
        if not skill:
            return None
        if name is not None:
            skill.name = name
        if trigger_keys is not None:
            skill.trigger_keys = trigger_keys
        if prompt_snippet is not None:
            skill.prompt_snippet = prompt_snippet
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def delete_skill(self, skill_id: uuid.UUID) -> bool:
        skill = await self.get_skill(skill_id)
        if skill:
            await self.db.delete(skill)
            await self.db.commit()
            return True
        return False
