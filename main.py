"""ASGI entry point for the regulation workbench."""
from app.server.application import create_app

app = create_app()
