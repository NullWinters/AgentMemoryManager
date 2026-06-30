import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import MemoryFragment, User


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_user(self, user_id: str) -> User:
        result = await self.db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(user_id=user_id)
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
        return user

    async def get_user(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def update_profile(self, user_id: str, profile: dict) -> User | None:
        user = await self.get_user(user_id)
        if not user:
            return None
        existing = user.profile or {}
        existing.update(profile)
        user.profile = existing
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete_user(self, user_id: str) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        await self.db.delete(user)
        await self.db.commit()
        return True

    async def add_memory_fragment(
        self,
        user_id: str,
        type: str,
        content: str,
        importance: float = 0.5,
        embedding: list[float] | None = None,
        source_msg_id: uuid.UUID | None = None,
    ) -> MemoryFragment:
        fragment = MemoryFragment(
            fragment_id=uuid.uuid4(),
            user_id=user_id,
            type=type,
            content=content,
            importance=importance,
            embedding=embedding,
            source_msg_id=source_msg_id,
        )
        self.db.add(fragment)
        await self.db.commit()
        await self.db.refresh(fragment)
        return fragment

    def _rows_to_results(self, rows) -> list[tuple[MemoryFragment, float | None]]:
        return [
            (
                MemoryFragment(
                    fragment_id=row.fragment_id,
                    user_id=row.user_id,
                    type=row.type,
                    content=row.content,
                    embedding=row.embedding,
                    importance=row.importance,
                    source_msg_id=row.source_msg_id,
                    accessed_at=row.accessed_at,
                    created_at=row.created_at,
                ),
                float(row.score) if row.score is not None else None,
            )
            for row in rows
        ]

    async def search_memories(
        self,
        user_id: str,
        query: str | None = None,
        vector: list[float] | None = None,
        top_k: int = 5,
        fragment_type: str | None = None,
    ) -> list[tuple[MemoryFragment, float | None]]:
        if vector is not None:
            vec_literal = "ARRAY[" + ",".join(str(v) for v in vector) + "]::vector"
            type_filter = "AND type = :ftype" if fragment_type else ""
            stmt = text(
                f"""
                SELECT fragment_id, user_id, type, content, embedding, importance,
                       source_msg_id, accessed_at, created_at,
                       1.0 - (embedding <=> {vec_literal}) AS score
                FROM memory_fragments
                WHERE user_id = :uid
                  AND embedding IS NOT NULL
                  {type_filter}
                ORDER BY embedding <=> {vec_literal}
                LIMIT :lim
                """
            )
            params: dict = {"uid": user_id, "lim": top_k}
            if fragment_type:
                params["ftype"] = fragment_type
            result = await self.db.execute(stmt, params)
            return self._rows_to_results(result.fetchall())

        if query:
            type_filter = "AND type = :ftype" if fragment_type else ""
            stmt = text(
                f"""
                SELECT fragment_id, user_id, type, content, embedding, importance,
                       source_msg_id, accessed_at, created_at,
                       ts_rank(to_tsvector('simple', content),
                               plainto_tsquery('simple', :query)) AS score
                FROM memory_fragments
                WHERE user_id = :uid
                  AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
                  {type_filter}
                ORDER BY score DESC
                LIMIT :lim
                """
            )
            params = {"query": query, "uid": user_id, "lim": top_k}
            if fragment_type:
                params["ftype"] = fragment_type
            result = await self.db.execute(stmt, params)
            return self._rows_to_results(result.fetchall())

        q = (
            select(MemoryFragment)
            .where(MemoryFragment.user_id == user_id)
            .order_by(MemoryFragment.created_at.desc())
            .limit(top_k)
        )
        if fragment_type:
            q = q.where(MemoryFragment.type == fragment_type)
        result = await self.db.execute(q)
        return [(frag, None) for frag in result.scalars().all()]

    async def delete_memory_fragment(
        self, user_id: str, fragment_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            select(MemoryFragment).where(
                MemoryFragment.fragment_id == fragment_id,
                MemoryFragment.user_id == user_id,
            )
        )
        fragment = result.scalar_one_or_none()
        if fragment:
            await self.db.delete(fragment)
            await self.db.commit()
            return True
        return False
