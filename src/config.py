import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://memory:memorypass@localhost:5432/memorydb",
)
MEMORY_API_KEY = os.getenv("MEMORY_API_KEY", "")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))
MAX_SESSION_TURNS = int(os.getenv("MAX_SESSION_TURNS", "20"))
USER_MEMORY_TOP_K = int(os.getenv("USER_MEMORY_TOP_K", "5"))
