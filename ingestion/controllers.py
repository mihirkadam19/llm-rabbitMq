# api and middleware controllers
from pydantic import BaseModel
import db
import uuid, os
from fastapi import HTTPException, APIRouter, Request
from helpers import publish

TENANT_NAME = os.environ["TENANT_NAME"]

db.init_db()
ingestion_router = APIRouter() 

class Tailor(BaseModel):
    job_description: str
    resume_text: str
    tailor_resume: bool = True
    tailor_cover_letter: bool = True

@ingestion_router.post("/tailor", status_code=202)
def submit(r: Request, t: Tailor):
    rid = str(uuid.uuid4())
    db.create_request(rid)
    publish({"request_id": rid, **t.model_dump()}, f"{TENANT_NAME}_queue")
    return {"request_id": rid}


@ingestion_router.get("/tailor/{rid}")
def status(r: Request, rid: str):
    row = db.get_response(rid)
    if not row:
        raise HTTPException(404, "request not found")
    return row