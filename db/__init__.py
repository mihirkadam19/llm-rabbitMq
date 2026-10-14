# db/__init__.py
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, RealDictCursor


@contextmanager
def _cursor():
    conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)
    try:
        with conn, conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


def init_db():
    with _cursor() as cur:
        cur.execute((Path(__file__).parent / "schema.sql").read_text())


def create_request(request_id):
    with _cursor() as cur:
        cur.execute("insert into responses (request_id) values (%s)", (request_id,))


def set_status(request_id, status, result=None, error=None):
    with _cursor() as cur:
        cur.execute(
            """update responses
               set status = %s, result = %s, error = %s, updated_at = now()
               where request_id = %s""",
            (status, Json(result) if result is not None else None, error, request_id),
        )


def get_response(request_id):
    with _cursor() as cur:
        cur.execute(
            """select request_id, status, result, error, created_at, updated_at
               from responses where request_id = %s""",
            (request_id,),
        )
        return cur.fetchone()