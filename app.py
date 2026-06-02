#!/usr/bin/env python3
# Copyright (C) 2026 AI News RSS Contributors
# Licensed under AGPL-3.0

"""
AI News RSS - Open Source Edition
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from models.database import init_db
from routes.daily import router as daily_router
from routes.rss import router as rss_router
from routes.news import router as news_router
from core.config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("Starting AI News RSS...")
    await init_db()
    logger.info("Database initialized")

    from core.news_poller import news_poller
    await news_poller.start_scheduled(
        hour=config.poller_hour,
        minute=config.poller_minute
    )
    logger.info(f"NewsPoller started: daily at {config.poller_hour:02d}:{config.poller_minute:02d}")

    yield

    from core.news_poller import news_poller
    await news_poller.stop()
    logger.info("AI News RSS stopped")


app = FastAPI(
    title="AI News RSS",
    description="AI-powered news aggregation system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    daily_file = Path(__file__).parent / "static" / "daily.html"
    if daily_file.exists():
        return FileResponse(str(daily_file))
    return {"message": "AI News RSS API", "version": "1.0.0"}


@app.get("/daily.html")
async def daily_page():
    from fastapi.responses import FileResponse
    f = Path(__file__).parent / "static" / "daily.html"
    if f.exists():
        return FileResponse(str(f))
    return {"message": "Page not found"}


@app.get("/rss.html")
async def rss_page():
    from fastapi.responses import FileResponse
    f = Path(__file__).parent / "static" / "rss.html"
    if f.exists():
        return FileResponse(str(f))
    return {"message": "Page not found"}


app.include_router(daily_router)
app.include_router(rss_router)
app.include_router(news_router)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

audio_dir = Path(__file__).parent / "data" / "audio"
audio_dir.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    logger.info(f"Starting AI News RSS on {host}:{port}")

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=debug,
    )
