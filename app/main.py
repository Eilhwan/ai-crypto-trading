from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger
import sys
import os

from database.db import init_db
from api.routes import router

# Configure loguru
logger.remove()
logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), colorize=True)
logger.add("logs/trading.log", rotation="1 day", retention="30 days", level="DEBUG")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Trading System...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="AI Crypto Trading System",
    description="뉴스 감성 분석 + 기술적 지표 기반 암호화폐 트레이딩 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": "AI Crypto Trading System",
        "version": "0.1.0",
        "docs": "/docs",
    }
