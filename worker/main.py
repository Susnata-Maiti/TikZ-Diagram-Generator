"""
Worker entry point for Vercel/Docker deployments.

Wraps the FastAPI backend so it can run as an independent containerized service.
The frontend calls this worker for all computationally intensive operations.
"""
from backend.main import app  # re-export the FastAPI app

if __name__ == "__main__":
    import uvicorn
    from backend.config import get_settings

    cfg = get_settings()
    uvicorn.run(
        "worker.main:app",
        host=cfg.app_host,
        port=cfg.app_port,
        reload=cfg.debug,
        log_level=cfg.log_level.lower(),
    )
