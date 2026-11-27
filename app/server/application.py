from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from app.agent.workflow import compile_graph, set_graph
from app.settings import cors_origins, langgraph_path, load
from app.server.routes import evaluations, health, knowledge, sessions


def create_app(store=None, tool_client=None):
    """tool_client is ignored; kept for older test call sites."""
    load()
    execution = sessions.Execution(store or sessions.Store())

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
                        yield
                finally:
                    app.state.memory_store = None
                    set_graph(None)
                    close = getattr(execution.store, "close", None)
                    if close:
                        close()

    app = FastAPI(title="管道规程工作台", lifespan=lifespan)
    app.state.execution = execution
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, sessions, knowledge, evaluations):
        app.include_router(module.router)
    return app
