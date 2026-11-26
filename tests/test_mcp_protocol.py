import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from mcp.shared.memory import create_connected_server_and_client_session
from rag import mcp_server


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_and_unpublished_schema(self):
        with TemporaryDirectory() as tmp, patch.object(mcp_server, "ROOT", Path(tmp)):
            async with create_connected_server_and_client_session(
                mcp_server.server
            ) as session:
                names = {tool.name for tool in (await session.list_tools()).tools}
                self.assertEqual(
                    names,
                    {
                        "get_calculation_schema",
                        "calculate_index",
                        "plot_curve",
                        "search_clauses",
                        "lookup_defect_score",
                    },
                )
                result = await session.call_tool(
                    "get_calculation_schema", {"calculation_type": "RI"}
                )
                self.assertEqual(
                    json.loads(result.content[0].text)["status"], "pending_review"
                )
                result = await session.call_tool("search_clauses", {"query": "1.0.1"})
                self.assertEqual(json.loads(result.content[0].text)["evidence"], [])
