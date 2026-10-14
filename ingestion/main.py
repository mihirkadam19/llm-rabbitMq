# ingestion/main.py
import os, json, uuid
import pika
from fastapi import FastAPI
from pydantic import BaseModel

QUEUE = "applications"
app = FastAPI()


class Application(BaseModel):
    job_description: str
    resume_text: str
    tailor_resume: bool = True
    tailor_cover_letter: bool = True


def publish(body: dict):
    conn = pika.BlockingConnection(pika.URLParameters(os.environ["RABBITMQ_URL"]))
    ch = conn.channel()
    ch.queue_declare(queue=QUEUE, durable=True)
    ch.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=json.dumps(body),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    conn.close()


@app.post("/applications", status_code=202)
def submit(a: Application):
    rid = str(uuid.uuid4())
    publish({"request_id": rid, **a.model_dump()})
    return {"request_id": rid}