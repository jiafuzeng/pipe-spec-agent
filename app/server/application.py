import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from app.agent.store import Store
from app.agent.workflow import compile_graph, set_graph
from app.config import langgraph_path
from app.server.routes import evaluations, health, knowledge, sessions


def create_app(store=None, tool_client=None):
    load_dotenv()
    execution = sessions.Execution(store or Store(), tool_client)

    @asynccontextmanager
    async def lifespan(app):
        path = langgraph_path(execution.store.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
            async with AsyncSqliteStore.from_conn_string(str(path)) as memory_store:
                await memory_store.setup()
                app.state.memory_store = memory_store
                set_graph(compile_graph(saver, memory_store))
                try:
                    async with knowledge.lifespan(app):
                        for row in execution.store.interrupted():
                            execution.submit(
                                row["sid"],
                                row["subject"],
                                row["message"],
                                recovering=row,
                            )
                        yield
                finally:
                    app.state.memory_store = None
                    if execution.tasks:
                        await asyncio.gather(*execution.tasks)
                    set_graph(None)

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
