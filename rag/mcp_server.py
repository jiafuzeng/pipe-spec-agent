"""Compatibility entrypoint. Prefer: python -m pipe_assessment_mcp."""

from pipe_assessment_mcp.server import main, server

__all__ = ["server", "main"]

if __name__ == "__main__":
    main()
