# ingestion/main.py
import os, json, uuid
import pika
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import db

db.init_db()
QUEUE = "applications"
app = FastAPI()


class Tailor(BaseModel):
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


@app.post("/tailor", status_code=202)
def submit(t: Tailor):
    rid = str(uuid.uuid4())
    db.create_request(rid)
    publish({"request_id": rid, **t.model_dump()})
    return {"request_id": rid}


@app.get("/applications/{rid}")
def status(rid: str):
    row = db.get_response(rid)
    if not row:
        raise HTTPException(404, "request not found")
    return row