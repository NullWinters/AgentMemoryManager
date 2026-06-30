import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import Message, Session
from src.services.user_service import UserService


class SessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self, agent_id: str, user_id: str, session_id: str = None
    ) -> Session:
        await UserService(self.db).get_or_create_user(user_id)
        session = Session(
            session_id=session_id or f"sess_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            user_id=user_id,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        result = await self.db.execute(
            select(Session).where(Session.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def update_session_status(self, session_id: str, status: str) -> Session | None:
        session = await self.get_session(session_id)
        if session:
            session.status = status
            await self.db.commit()
            await self.db.refresh(session)
        return session

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: str = None,
        tool_call_id: str = None,
    ) -> Message:
        message = Message(
            message_id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        self.db.add(message)
        await self.db.execute(
            update(Session)
            .where(Session.session_id == session_id)
            .values(message_count=Session.message_count + 1, updated_at=func.now())
        )
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(self, session_id: str, limit: int = 50) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
