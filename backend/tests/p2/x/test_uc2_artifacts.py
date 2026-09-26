"""P4.1.2 (UC2 part): the reference script reproduces expected/paperN_params.json exactly;
section names drift between the two papers."""
import filecmp
import json
import shutil
import subprocess
import sys
from pathlib import Path

UC2 = Path(__file__).resolve().parents[4] / "data" / "artifacts" / "uc2"
KEYS = ["title", "method", "datasets", "metrics", "main_result"]


def test_reference_reproduces_expected(tmp_path):
    copy = tmp_path / "uc2"
    shutil.copytree(UC2, copy)
    before = tmp_path / "before"
    shutil.copytree(copy / "expected", before)
    proc = subprocess.run([sys.executable, "reference.py"], cwd=copy, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in before.iterdir()) == ["paper1_params.json", "paper2_params.json"]
    for p in before.iterdir():
        assert filecmp.cmp(p, copy / "expected" / p.name, shallow=False), p.name


def test_param_keys_and_drift():
    for n in (1, 2):
        params = json.loads((UC2 / "expected" / f"paper{n}_params.json").read_text(encoding="utf-8"))
        assert list(params) == KEYS and all(params.values())
    p1, p2 = ((UC2 / f"paper{n}.txt").read_text(encoding="utf-8") for n in (1, 2))
    assert "2. Method" in p1 and "2 APPROACH" in p2   # the tool must absorb renamed sections
