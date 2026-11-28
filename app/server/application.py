import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from app import settings
from app.agent.workflow import compile_graph, set_graph
from app.server.routes import chat, evaluations, health, knowledge


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        path = Path(os.getenv("LANGGRAPH_DB", str(settings.LANGGRAPH_DB)))
        path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(path)) as checkpointer:
            async with AsyncSqliteStore.from_conn_string(str(path)) as memory_store:
                await memory_store.setup()
                app.state.store = memory_store
                app.state.checkpointer = checkpointer
                set_graph(compile_graph(checkpointer, memory_store))
                yield
                set_graph(None)

    app = FastAPI(title="管道规程工作台", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.CORS_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, chat, knowledge, evaluations):
        app.include_router(module.router)
    return app
