import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mcp.shared.memory import create_connected_server_and_client_session

from pipe_assessment_mcp import server as mcp_server
from pipe_assessment_mcp import storage


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_exclude_search_and_unpublished_schema(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(storage, "data_root", return_value=root):
                (root / "artifacts").mkdir(parents=True, exist_ok=True)
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
                            "lookup_defect_score",
                        },
                    )
                    self.assertNotIn("search_clauses", names)
                    result = await session.call_tool(
                        "get_calculation_schema", {"calculation_type": "RI"}
                    )
                    self.assertEqual(
                        json.loads(result.content[0].text)["status"], "pending_review"
                    )
