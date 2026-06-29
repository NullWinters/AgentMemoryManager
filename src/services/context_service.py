from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ContextService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def compose_context(
        self,
        agent_id: str,
        user_id: str,
        session_id: str,
        query: str = None,
        top_k: int = 5,
        query_embedding: list[float] | None = None,
    ) -> dict:
        if query_embedding is not None:
            vec_literal = "ARRAY[" + ",".join(str(v) for v in query_embedding) + "]::vector"
            stmt = text(
                f"SELECT sp_compose_context(:agent_id, :user_id, :session_id, :top_k, {vec_literal})"
            )
        else:
            stmt = text(
                "SELECT sp_compose_context(:agent_id, :user_id, :session_id, :top_k)"
            )

        params = {
            "agent_id": agent_id,
            "user_id": user_id,
            "session_id": session_id,
            "top_k": top_k,
        }
        result = await self.db.execute(stmt, params)
        row = result.scalar_one()
        context = row if isinstance(row, dict) else row
        return context
