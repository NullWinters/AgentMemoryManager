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
from src.models.database import (
    Agent,
    Message,
    MemoryFragment,
    Session,
    User,
)

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


class LLMService:
    @staticmethod
    async def run_post_message(
        session_id: str,
        message_id: uuid.UUID,
        content: str,
        agent_id: str,
        user_id: str,
    ) -> None:
        async with async_session() as db:
            agent_result = await db.execute(
                select(Agent).where(Agent.agent_id == agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if not agent:
                return

            llm_config = agent.config.get("llm", {})
            embed_config = agent.config.get("embedding", {})
            if not embed_config:
                embed_config = llm_config

            chat_provider = _create_provider(llm_config, "gpt-4o-mini")
            embed_provider = _create_provider(embed_config, "text-embedding-3-small")

            if not chat_provider:
                return

            embedder = None
            if embed_provider:
                embedder = TextEmbedder(embed_provider)

            summarizer = SessionSummarizer(chat_provider)
            extractor = MemoryExtractor(chat_provider)

            if embedder:
                emb = await embedder.embed(content)
                if emb:
                    await db.execute(
                        update(Message)
                        .where(Message.message_id == message_id)
                        .values(embedding=emb)
                    )

            msg_count_result = await db.execute(
                select(func.count()).where(Message.session_id == session_id)
            )
            msg_count = msg_count_result.scalar_one()
            threshold = 40
            if msg_count > threshold:
                msgs_result = await db.execute(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at)
                )
                all_msgs = msgs_result.scalars().all()
                msgs_data = [
                    {"role": m.role, "content": m.content} for m in all_msgs
                ]

                summary = await summarizer.summarize(msgs_data)
                if summary:
                    await db.execute(
                        update(Session)
                        .where(Session.session_id == session_id)
                        .values(summary=summary)
                    )

                extracted = await extractor.extract(msgs_data)
                for frag in extracted.get("fragments", []):
                    frag_emb = None
                    if embedder:
                        frag_emb = await embedder.embed(frag["content"])
                    db.add(
                        MemoryFragment(
                            fragment_id=uuid.uuid4(),
                            user_id=user_id,
                            type=frag["type"],
                            content=frag["content"],
                            embedding=frag_emb,
                            importance=frag["importance"],
                        )
                    )

                profile_updates = extracted.get("profile_updates", {})
                if profile_updates:
                    user_result = await db.execute(
                        select(User).where(User.user_id == user_id)
                    )
                    user_row = user_result.scalar_one_or_none()
                    if user_row:
                        existing = user_row.profile or {}
                        existing.update(profile_updates)
                        user_row.profile = existing

            await db.commit()
