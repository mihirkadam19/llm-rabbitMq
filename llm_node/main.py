# llm_node/main.py
import os, json, time
from typing import TypedDict
import anthropic, pika
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy
import db

QUEUE = "applications"
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
llm = anthropic.Anthropic()


class State(TypedDict, total=False):
    job_description: str
    resume_text: str
    tailor_resume: bool
    tailor_cover_letter: bool
    tailored_resume: str
    cover_letter: str


def ask(system, prompt):
    r = llm.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    return "".join(b.text for b in r.content if b.type == "text")


def tailor(s: State):
    ctx = f"JOB\n{s['job_description']}\n\nRESUME\n{s['resume_text']}"
    out = {}
    if s["tailor_resume"]:
        out["tailored_resume"] = ask("Tailor this resume to the job. Keep facts intact.", ctx)
    if s["tailor_cover_letter"]:
        out["cover_letter"] = ask("Write a concise, specific cover letter grounded in the resume.", ctx)
    return out

def buildGraph():
    s = State
    g = StateGraph(s)
    g.add_node("tailor", tailor, retry_policy=RetryPolicy(max_attempts=3))
    g.add_edge(START, "tailor")
    g.add_edge("tailor", END)
    graph = g.compile()
    return graph


def handle(ch, method, props, body):
    job = json.loads(body)
    rid = job.pop("request_id")
    try:
        graph = buildGraph()
        db.set_status(rid, "processing")
        out = graph.invoke(job)
        db.set_status(rid, "completed", result=out)
        print(json.dumps({"request_id": rid, **out}, indent=2), flush=True)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        db.set_status(rid, "failed", error=str(e))
        print(f"request {rid} failed {e}", flush=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def connect():
    for _ in range(30):
        try:
            return pika.BlockingConnection(pika.URLParameters(os.environ["RABBITMQ_URL"]))
        except pika.exceptions.AMQPConnectionError:
            print("rabbitmq not ready, retrying", flush=True)
            time.sleep(2)
    raise RuntimeError("rabbitmq unreachable")

def main():
    conn = connect()
    ch = conn.channel()
    ch.queue_declare(queue=QUEUE, durable=True)
    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=QUEUE, on_message_callback=handle)
    print("llm node ready", flush=True)
    ch.start_consuming()

def debug():
    graph = buildGraph()
    job = json.load(open("./llm_node/debug/payload.json"))
    print(json.dumps(graph.invoke(job), indent=2))

if __name__ == "__main__":
    debug() if os.environ.get("DEBUG") else main()