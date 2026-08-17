"""
Database handle, importable without dragging in the whole API.

server.py builds its Motor client at module scope, so `import server` starts the
agent pool, the snapshot poller and the FastAPI app. A Temporal worker needs the
database and none of that, and importing server just to reach `db` would mean
every worker process quietly runs a second copy of the pollers.

Lazily constructed so importing this module never opens a connection — the
workflow definitions import it at call time, and tests import it without needing
Mongo running at all.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


@lru_cache(maxsize=1)
def get_client() -> AsyncIOMotorClient:
    url = os.environ.get("MONGO_URL")
    if not url:
        raise RuntimeError("MONGO_URL is not set")
    return AsyncIOMotorClient(url)


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[os.environ.get("DB_NAME", "yabbai_local")]
