import os
import unittest


class AgentL0Tests(unittest.TestCase):
    def test_ci_suite_runs(self):
        os.environ["MCP_INLINE"] = "1"
        os.environ["EVIDENCE_LLM_VERIFY"] = "0"
        from agentEval.run import run_suite

        report = run_suite("ci")
        self.assertGreaterEqual(report["summary"]["total"], 1)
        failed = [r for r in report["results"] if not r.get("passed") and not r.get("skipped")]
        self.assertEqual(failed, [], msg=failed)


if __name__ == "__main__":
    unittest.main()
