from fastapi import APIRouter

from app.api.v1.routes import approvals, health, metrics, runs, tasks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(runs.router)
api_router.include_router(approvals.router)
api_router.include_router(metrics.router)
