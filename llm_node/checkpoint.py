# checkpoint.py
import os, asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

_pool = None
_checkpointer = None


async def get_checkpointer():
    global _pool, _checkpointer
    if _checkpointer is None:
        _pool = AsyncConnectionPool(
            conninfo=os.environ["DATABASE_URL"],
            max_size=10,
            open=False,
            kwargs=dict(autocommit=True, prepare_threshold=0, row_factory=dict_row),
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer():
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None