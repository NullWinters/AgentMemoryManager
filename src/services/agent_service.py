import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import Agent, Skill, SkillAgent


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_agent(
        self, agent_id: str, name: str, persona: str = "", config: dict | None = None
    ) -> Agent:
        agent = Agent(
            agent_id=agent_id,
            name=name,
            persona=persona,
            config=config or {},
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get_agent(self, agent_id: str) -> Agent | None:
        result = await self.db.execute(select(Agent).where(Agent.agent_id == agent_id))
        return result.scalar_one_or_none()

    async def update_agent(
        self,
        agent_id: str,
        name: str | None = None,
        persona: str | None = None,
        config: dict | None = None,
        status: str | None = None,
    ) -> Agent | None:
        agent = await self.get_agent(agent_id)
        if not agent:
            return None
        if name is not None:
            agent.name = name
        if persona is not None:
            agent.persona = persona
        if config is not None:
            agent.config = config
        if status is not None:
            agent.status = status
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def add_skill_to_agent(self, agent_id: str, skill_id: uuid.UUID) -> SkillAgent:
        if not await self.get_agent(agent_id):
            raise ValueError("Agent not found")

        skill = await self.db.execute(select(Skill).where(Skill.skill_id == skill_id))
        if not skill.scalar_one_or_none():
            raise ValueError("Skill not found")

        duplicate = await self.db.execute(
            select(SkillAgent).where(
                SkillAgent.agent_id == agent_id,
                SkillAgent.skill_id == skill_id,
            )
        )
        if duplicate.scalar_one_or_none():
            raise ValueError("Skill already bound to agent")

        sa = SkillAgent(skill_id=skill_id, agent_id=agent_id)
        self.db.add(sa)
        await self.db.commit()
        return sa

    async def remove_skill_from_agent(self, agent_id: str, skill_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(SkillAgent).where(
                SkillAgent.agent_id == agent_id,
                SkillAgent.skill_id == skill_id,
            )
        )
        sa = result.scalar_one_or_none()
        if sa:
            await self.db.delete(sa)
            await self.db.commit()
            return True
        return False

    async def update_skill_binding(
        self, agent_id: str, skill_id: uuid.UUID, enabled: bool
    ) -> SkillAgent | None:
        result = await self.db.execute(
            select(SkillAgent).where(
                SkillAgent.agent_id == agent_id,
                SkillAgent.skill_id == skill_id,
            )
        )
        sa = result.scalar_one_or_none()
        if not sa:
            return None
        sa.enabled = enabled
        await self.db.commit()
        await self.db.refresh(sa)
        return sa

    async def get_agent_skills(self, agent_id: str) -> list[Skill]:
        result = await self.db.execute(
            select(Skill)
            .join(SkillAgent)
            .where(SkillAgent.agent_id == agent_id, SkillAgent.enabled == True)
        )
        return list(result.scalars().all())

    async def delete_agent(self, agent_id: str) -> bool:
        agent = await self.get_agent(agent_id)
        if not agent:
            return False
        await self.db.delete(agent)
        await self.db.commit()
        return True

    async def get_agent_skill_bindings(self, agent_id: str) -> list[SkillAgent]:
        result = await self.db.execute(
            select(SkillAgent).where(SkillAgent.agent_id == agent_id)
        )
        return list(result.scalars().all())
