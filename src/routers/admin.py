from fastapi import APIRouter
from sqlalchemy import text

from src.database import async_session

router = APIRouter(tags=["admin"])


@router.get("/health")
async def health():
    pgvector_ok = False
    try:
        async with async_session() as db:
            result = await db.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            row = result.fetchone()
            pgvector_ok = row is not None
    except Exception:
        pgvector_ok = False

    return {
        "status": "ok",
        "pgvector": pgvector_ok,
    }


@router.get("/stats")
async def stats():
    async with async_session() as db:
        result = await db.execute(
            text("SELECT * FROM v_memory_stats")
        )
        rows = result.fetchall()
        memory_stats = [
            {
                "user_id": row[0],
                "total_fragments": row[1],
                "avg_importance": float(row[2]) if row[2] else 0.0,
                "type_count": row[3],
                "last_memory_at": row[4].isoformat() if row[4] else None,
            }
            for row in rows
        ]

    return {
        "memory_stats": memory_stats,
    }
