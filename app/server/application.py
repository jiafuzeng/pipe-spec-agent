import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.store import Store
from app.server.routes import evaluations, health, knowledge, sessions


def create_app(store=None, tool_client=None):
    load_dotenv()
    execution = sessions.Execution(store or Store(), tool_client)

    @asynccontextmanager
    async def lifespan(app):
        async with knowledge.lifespan(app):
            for row in execution.store.interrupted():
                execution.submit(
                    row["sid"], row["subject"], row["message"], recovering=row
                )
            try:
                yield
            finally:
                if execution.tasks:
                    await asyncio.gather(*execution.tasks)

    app = FastAPI(title="管道规程工作台", lifespan=lifespan)
    app.state.execution = execution
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
            ).split(",")
            if origin.strip()
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, sessions, knowledge, evaluations):
        app.include_router(module.router)
    return app
