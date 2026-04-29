"""GTM Automation API entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_shared import APP_HOST, APP_PORT, CORS_ORIGINS, vtlog
import api_auth
import api_companies
import api_contact_enrichment
import api_contacts
import api_conversations
import api_enrichment
import api_experiments
import api_exports
import api_feedback
import api_health
import api_icps
import api_leads
import api_metrics
import api_orchestration
import api_outreach
import api_pipeline
import api_projects
import api_quality
import api_replies
import api_sends
import api_signals
import api_suppression
import api_tuning
from auth import get_current_user
from middleware import RateLimitMiddleware, StructuredLoggingMiddleware, init_sentry
from startup import install_defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_sentry()
    summary = install_defaults()
    vtlog.info("api_started", **summary)
    yield
    vtlog.info("api_stopped")


app = FastAPI(title="GTM Automation API", version="1.0.0", lifespan=lifespan)

# Middleware order: outer-first. CORS added LAST so it wraps everything.
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Public routes (no auth required)
app.include_router(api_health.router)
app.include_router(api_auth.router)

# Authenticated routes — bearer token required
auth_dep = [Depends(get_current_user)]
app.include_router(api_projects.router, dependencies=auth_dep)
app.include_router(api_icps.router, dependencies=auth_dep)
app.include_router(api_contacts.router, dependencies=auth_dep)
app.include_router(api_companies.router, dependencies=auth_dep)
app.include_router(api_pipeline.router, dependencies=auth_dep)
app.include_router(api_suppression.router, dependencies=auth_dep)
app.include_router(api_enrichment.router, dependencies=auth_dep)
app.include_router(api_contact_enrichment.router, dependencies=auth_dep)
app.include_router(api_signals.router, dependencies=auth_dep)
app.include_router(api_leads.router, dependencies=auth_dep)
app.include_router(api_metrics.router, dependencies=auth_dep)
app.include_router(api_quality.router, dependencies=auth_dep)
app.include_router(api_outreach.router, dependencies=auth_dep)
app.include_router(api_sends.router, dependencies=auth_dep)
app.include_router(api_replies.router, dependencies=auth_dep)
app.include_router(api_experiments.router, dependencies=auth_dep)
app.include_router(api_exports.router, dependencies=auth_dep)
app.include_router(api_feedback.router, dependencies=auth_dep)
app.include_router(api_tuning.router, dependencies=auth_dep)
app.include_router(api_orchestration.router, dependencies=auth_dep)
app.include_router(api_conversations.router, dependencies=auth_dep)


@app.get("/")
def root() -> dict:
    return {"name": "GTM Automation API", "version": "1.0.0"}


if __name__ == "__main__":
    vtlog.info("api_start", host=APP_HOST, port=APP_PORT)
    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
