from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from stocktopus.api.analyze import router as analyze_router
from stocktopus.api.candles import router as candles_router
from stocktopus.api.context import router as context_router
from stocktopus.api.news import router as news_router
from stocktopus.api.paper import paper_router
from stocktopus.api.strategy import router as strategy_router
from stocktopus.config import get_settings
from stocktopus.logging_config import configure_logging

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    logger.info("Stocktopus starting", env=settings.env, version=VERSION)
    yield
    logger.info("Stocktopus shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Stocktopus API",
        description="AI-assisted trading research and execution system",
        version=VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["http://localhost:3000", "http://localhost:5173"]
            if not settings.is_production
            else []
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION, "env": settings.env}

    app.include_router(candles_router)
    app.include_router(news_router)
    app.include_router(context_router)
    app.include_router(analyze_router)
    app.include_router(strategy_router)
    app.include_router(paper_router)

    return app


app = create_app()
