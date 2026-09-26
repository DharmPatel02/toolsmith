import filecmp
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
UC1 = ROOT / "data" / "artifacts" / "uc1"


class UC1ArtifactTests(unittest.TestCase):
    def test_reference_script_reproduces_expected_files_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_root = Path(tmp) / "uc1"
            shutil.copytree(UC1, copy_root)
            expected_before = copy_root / "expected_before"
            shutil.copytree(copy_root / "expected", expected_before)

            proc = subprocess.run(
                [sys.executable, "reference.py"],
                cwd=copy_root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            for path in sorted(expected_before.iterdir()):
                regenerated = copy_root / "expected" / path.name
                self.assertTrue(regenerated.exists(), path.name)
                self.assertTrue(filecmp.cmp(path, regenerated, shallow=False), path.name)

    def test_week_three_uses_renamed_columns(self):
        from openpyxl import load_workbook

        wb = load_workbook(UC1 / "week3.xlsx", read_only=True)
        headers = [cell.value for cell in wb["Sales"][1]]

        self.assertEqual(headers, ["Sales Region", "Business Line", "Net Revenue"])


if __name__ == "__main__":
    unittest.main()
