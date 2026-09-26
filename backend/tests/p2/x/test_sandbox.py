import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.sandbox.runner import run_in_sandbox

PIVOT_TOOL = r'''
def main(ctx, **params):
    rows = ctx.read_table("sales.csv")
    if hasattr(rows, "groupby"):
        summary = rows.groupby("region", as_index=False)["sales"].sum()
        total = int(summary["sales"].sum())
        ctx.write_output("pivot.csv", summary)
        return {"total": total, "regions": len(summary)}

    totals = {}
    for row in rows:
        totals[row["region"]] = totals.get(row["region"], 0) + int(row["sales"])
    ctx.write_output("pivot.json", totals)
    return {"total": sum(totals.values()), "regions": len(totals)}
'''


class SandboxRunnerTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_pivot_tool_dry_run_records_write_without_materializing(self):
        result = self.run_async(
            run_in_sandbox(
                PIVOT_TOOL,
                "main",
                {},
                {"sales.csv": "region,sales\nEast,10\nWest,7\nEast,5\n"},
                "dry_run",
                [],
                timeout_s=5,
            )
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.output["total"], 22)
        self.assertEqual(result.output["regions"], 2)
        self.assertEqual(len(result.intended_writes), 1)
        self.assertIn(result.intended_writes[0].path, {"pivot.csv", "pivot.json"})

    def test_fetch_requires_net_scope(self):
        result = self.run_async(
            run_in_sandbox(
                "def main(ctx, **params):\n    ctx.fetch('https://example.com')\n",
                "main",
                {},
                {},
                "dry_run",
                [],
                timeout_s=5,
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("network access requires", result.error or "")

    def test_timeout_kills_infinite_loop(self):
        result = self.run_async(
            run_in_sandbox(
                "def main(ctx, **params):\n    while True:\n        pass\n",
                "main",
                {},
                {},
                "dry_run",
                [],
                timeout_s=1,
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "timeout after 1s")


if __name__ == "__main__":
    unittest.main()
