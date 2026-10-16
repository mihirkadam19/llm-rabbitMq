# ingestion/main.py
import os
from fastapi import FastAPI
from controllers import ingestion_router
from middleware import TenantAuthMiddleware

TENANT_NAME = os.environ["TENANT_NAME"]

app = FastAPI()
app.add_middleware(TenantAuthMiddleware, tenant=TENANT_NAME)
app.include_router(ingestion_router, prefix=f"/api/v1/{TENANT_NAME}")