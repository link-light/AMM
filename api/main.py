"""
FastAPI Application - Main entry point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import analytics, costs, gateway, human_tasks, signals, skills, tasks
from core.config import settings
from core.database import close_db, init_db
from core.queue import queue_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.app.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting up AMM API...")
    
    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed (may already exist): {e}")
    
    # Initialize Redis
    try:
        await queue_manager.connect()
        logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise
    
    logger.info("AMM API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down AMM API...")
    
    await close_db()
    await queue_manager.disconnect()
    
    logger.info("AMM API shut down successfully")


# Create FastAPI app
app = FastAPI(
    title="AI Money Machine API",
    description="AI-driven multi-agent system for automated business opportunity discovery and execution",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app.debug else None,
    redoc_url="/redoc" if settings.app.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app.debug else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "environment": settings.app.environment,
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "name": "AI Money Machine",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# Include routers
app.include_router(signals.router, prefix="/api/signals", tags=["Signals"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(human_tasks.router, prefix="/api/human-tasks", tags=["Human Tasks"])
app.include_router(costs.router, prefix="/api/costs", tags=["Costs"])
app.include_router(skills.router, prefix="/api/skills", tags=["Skills"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(gateway.router, prefix="/api/gateway", tags=["Gateway"])

# TODO: Add WebSocket endpoint
# from api.websocket import websocket_endpoint
# app.add_websocket_route("/ws/events", websocket_endpoint)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app.debug,
        log_level=settings.app.log_level.lower(),
    )
