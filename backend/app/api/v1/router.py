from fastapi import APIRouter

from app.api.v1 import artifacts, benchmarks, projects, runs, settings_dashboard

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(projects.router)
api_v1_router.include_router(runs.router)
api_v1_router.include_router(artifacts.router)
api_v1_router.include_router(benchmarks.router)
api_v1_router.include_router(settings_dashboard.router)


@api_v1_router.get("/health", tags=["health"])
def health_v1() -> dict[str, str]:
    return {"status": "ok", "service": "veridra-api"}
