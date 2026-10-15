# checkpoint.py
import os
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool = None
_checkpointer = None


def get_checkpointer():
    global _pool, _checkpointer
    if _checkpointer is None:
        _pool = ConnectionPool(
            conninfo=os.environ["DATABASE_URL"],
            max_size=10,
            kwargs=dict(autocommit=True, prepare_threshold=0, row_factory=dict_row),
        )
        _checkpointer = PostgresSaver(_pool)
        _checkpointer.setup()
    return _checkpointer


def close_checkpointer():
    global _pool, _checkpointer
    if _pool is not None:
        _pool.close()
    _pool = None
    _checkpointer = None