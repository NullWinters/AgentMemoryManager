import logging
import uuid

from sqlalchemy import func, select, update

from src.database import async_session
from src.llm import (
    LLMProvider,
    MemoryExtractor,
    SessionSummarizer,
    TextEmbedder,
)
from src.models.database import Agent, Message, MemoryFragment, Session
from src.services.user_service import UserService

logger = logging.getLogger(__name__)


def _create_provider(config: dict, model_default: str) -> LLMProvider | None:
    key = config.get("api_key")
    if not key:
        return None
    return LLMProvider(
        api_key=key,
        base_url=config.get("base_url"),
        model=config.get("model", model_default),
    )


THRESHOLD = 40


class LLMService:
    @staticmethod
    async def _read_data(agent_id: str, session_id: str) -> dict | None:
        async with async_session() as db:
            agent_result = await db.execute(
                select(Agent).where(Agent.agent_id == agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if not agent:
                return None

            llm_config = agent.config.get("llm", {})
            embed_config = agent.config.get("embedding", {})
            if not embed_config:
                embed_config = llm_config

            if not llm_config.get("api_key"):
                return None

            msg_count_result = await db.execute(
                select(func.count()).where(Message.session_id == session_id)
            )
            msg_count = msg_count_result.scalar_one()

            msgs_data = None
            if msg_count > THRESHOLD:
                msgs_result = await db.execute(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at)
                )
                all_msgs = msgs_result.scalars().all()
                msgs_data = [
                    {"role": m.role, "content": m.content} for m in all_msgs
                ]

        return {
            "llm_config": llm_config,
            "embed_config": embed_config,
            "msgs_data": msgs_data,
        }

    @staticmethod
    async def _write_results(
        session_id: str,
        message_id: uuid.UUID,
        user_id: str,
        results: dict,
    ) -> None:
        async with async_session() as db:
            emb = results.get("embedding")
            if emb is not None:
                await db.execute(
                    update(Message)
                    .where(Message.message_id == message_id)
                    .values(embedding=emb)
                )

            if results.get("threshold_exceeded"):
                if results.get("summary"):
                    await db.execute(
                        update(Session)
                        .where(Session.session_id == session_id)
                        .values(summary=results["summary"])
                    )

                user_svc = UserService(db)
                await user_svc.get_or_create_user(user_id)
                for frag in results.get("fragments", []):
                    db.add(
                        MemoryFragment(
                            fragment_id=uuid.uuid4(),
                            user_id=user_id,
                            type=frag["type"],
                            content=frag["content"],
                            embedding=frag.get("embedding"),
                            importance=frag["importance"],
                        )
                    )

                profile_updates = results.get("profile_updates", {})
                if profile_updates:
                    user_row = await user_svc.get_or_create_user(user_id)
                    existing = user_row.profile or {}
                    existing.update(profile_updates)
                    user_row.profile = existing

            await db.commit()

    @staticmethod
    async def run_post_message(
        session_id: str,
        message_id: uuid.UUID,
        content: str,
        agent_id: str,
        user_id: str,
    ) -> None:
        data = await LLMService._read_data(agent_id, session_id)
        if not data:
            return

        chat_provider = _create_provider(data["llm_config"], "gpt-4o-mini")
        embed_provider = _create_provider(data["embed_config"], "text-embedding-3-small")
        embedder = TextEmbedder(embed_provider) if embed_provider else None

        results: dict = {}

        if embedder:
            emb = await embedder.embed(content)
            if emb is not None:
                results["embedding"] = emb

        if data["msgs_data"] is not None:
            results["threshold_exceeded"] = True
            summarizer = SessionSummarizer(chat_provider)
            extractor = MemoryExtractor(chat_provider)

            summary = await summarizer.summarize(data["msgs_data"])
            results["summary"] = summary

            extracted = await extractor.extract(data["msgs_data"])
            for frag in extracted.get("fragments", []):
                if embedder:
                    frag_emb = await embedder.embed(frag["content"])
                    if frag_emb is not None:
                        frag["embedding"] = frag_emb
            results["fragments"] = extracted.get("fragments", [])
            results["profile_updates"] = extracted.get("profile_updates", {})

        await LLMService._write_results(session_id, message_id, user_id, results)
