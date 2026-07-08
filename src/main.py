"""
FastAPI application entry point for ArxivAI v2.0
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from src.config import get_settings
from src.database import create_all_tables, close_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    App lifecycle manager: startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting ArxivAI v2.0")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    
    # Create database tables
    await create_all_tables()
    logger.info("✅ Database initialized")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down ArxivAI")
    await close_db()
    logger.info("✅ Cleanup complete")


# ─────────────────────────────────────────────────────────────
# Create FastAPI App
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-user agentic RAG system for academic research",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────
# CORS Middleware
# ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=settings.ALLOW_METHODS,
    allow_headers=settings.ALLOW_HEADERS,
)


# ─────────────────────────────────────────────────────────────
# Health Check Endpoint
# ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Returns: Application status
    """
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


# ─────────────────────────────────────────────────────────────
# Root Endpoint
# ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    """
    API root endpoint.
    """
    return {
        "message": "Welcome to ArxivAI v2.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


# ─────────────────────────────────────────────────────────────
# Prometheus Custom HTTP Middleware
# ─────────────────────────────────────────────────────────────
from prometheus_client import Counter, Histogram
import time

# Define metrics matching standard Grafana dashboard queries
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

@app.middleware("http")
async def prometheus_middleware(request, call_next):
    method = request.method
    endpoint = request.url.path
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Do not track Prometheus scraping of `/metrics` itself to prevent spam
    if not (endpoint.startswith("/metrics") or endpoint.startswith("/favicon")):
        status = str(response.status_code)
        HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=status).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)
        
    return response


# ─────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────
from src.auth.router import router as auth_router
from src.papers.router import router as papers_router
from src.collaboration.router import router as collab_router
from src.query.router import router as query_router

app.include_router(auth_router)
app.include_router(papers_router)
app.include_router(collab_router)
app.include_router(query_router)


# ─────────────────────────────────────────────────────────────
# Prometheus Metrics
# ─────────────────────────────────────────────────────────────
from prometheus_client import make_asgi_app
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=settings.FASTAPI_HOST,
        port=settings.FASTAPI_PORT,
    )