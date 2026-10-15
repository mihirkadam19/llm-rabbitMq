import functools, logging, time
from contextvars import ContextVar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("llm_node")
request_id = ContextVar("request_id", default="none")


def traced(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        log.info("%s start rid=%s", fn.__name__, request_id.get())
        try:
            return await fn(*args, **kwargs)
        except Exception:
            log.exception("%s failed rid=%s", fn.__name__, request_id.get())
            raise
        finally:
            log.info("%s done rid=%s took=%.2fs", fn.__name__, request_id.get(), time.perf_counter() - start)
    return wrapper