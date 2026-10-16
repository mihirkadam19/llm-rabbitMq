# llm_node/main.py
import os, json, time, asyncio
from typing import TypedDict
import anthropic, aio_pika
from functools import partial
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy
from checkpoint import get_checkpointer, close_checkpointer
import db
from custom_logger import traced
import logging

logging.basicConfig(
    level=logging.INFO,                           
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',                  
    filename='app.log',                           
    filemode='w'
)

QUEUE = os.environ.get("QUEUE", "applications")
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
llm = anthropic.AsyncAnthropic()


class State(TypedDict, total=False):
    job_description: str
    resume_text: str
    tailor_resume: bool
    tailor_cover_letter: bool
    tailored_resume: str
    cover_letter: str


@traced
async def ask(system, prompt):
    r = await llm.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    return "".join(b.text for b in r.content if b.type == "text")


async def tailor_resume(s: State):
    ctx = f"JOB\n{s['job_description']}\n\nRESUME\n{s['resume_text']}"
    out = {}
    if s["tailor_resume"]:
        out["tailored_resume"] = await ask("Tailor this resume to the job. Keep facts intact.", ctx)
    return out

async def tailor_cover_letter(s: State):
    ctx = f"JOB\n{s['job_description']}\n\nRESUME\n{s['resume_text']}"
    out = {}
    if s["tailor_cover_letter"]:
        out["cover_letter"] = await ask("Write a concise, specific cover letter grounded in the resume.", ctx)
    return out

def route_cover_letter(s: State):
    if s["tailor_cover_letter"]:
        return "tailor_cover_letter_path"
    return "end_path"


def buildGraph():
    g = StateGraph(State)
    g.add_node("resume", tailor_resume, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("cover_letter", tailor_cover_letter, retry_policy=RetryPolicy(max_attempts=3))
    g.add_edge(START, "resume")
    g.add_conditional_edges(
        "resume",
        route_cover_letter,
        {"tailor_cover_letter_path": "cover_letter", "end_path": END},
    )
    return g

@traced
async def handle(graph, message: aio_pika.IncomingMessage):
    job = json.loads(message.body)
    rid = job.pop("request_id")
    try:
        config = {"configurable": {"thread_id": rid}}
        await asyncio.to_thread(db.set_status, rid, "processing")
        out = await graph.ainvoke(job, config=config)
        await asyncio.to_thread(db.set_status, rid, "completed", result=out)
        logging.info(json.dumps({"request_id": rid, "status": "completed"}, indent=2))
        await message.ack()
    except Exception as e:
        await asyncio.to_thread(db.set_status, rid, "failed", error=str(e))
        logging.info(f"request {rid} failed {e}")
        await message.reject(requeue=False)

async def connect():
    for _ in range(30):
        try:
            return await aio_pika.connect_robust(os.environ["RABBITMQ_URL"])
        except (aio_pika.exceptions.AMQPConnectionError, OSError):
            logging.info("rabbitmq not ready, retrying")
            await asyncio.sleep(2)
    raise RuntimeError("rabbitmq unreachable")

async def main():
    checkpointer = await get_checkpointer()
    graph = buildGraph().compile(checkpointer=checkpointer)

    conn = await connect()
    try:
        channel = await conn.channel()
        await channel.set_qos(prefetch_count=10)
        queue = await channel.declare_queue(QUEUE, durable=True)
        await queue.consume(partial(handle, graph))
        logging.info("llm node ready")
        await asyncio.Future()
    finally:
        await conn.close()
        await close_checkpointer()

async def debug():
    graph = buildGraph().compile()
    job = json.load(open("./llm_node/debug/payload.json"))
    config = {"configurable": {"thread_id": "1111-aaaa-bbb"}}
    result = await graph.ainvoke(job, config=config)
    logging.info(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(debug()) if os.environ.get("DEBUG") else asyncio.run(main())