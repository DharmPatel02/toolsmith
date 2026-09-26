from __future__ import annotations

import csv
import glob
import json
import os
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse


FETCH_MAP_INPUT = "__fetch_map__"


@dataclass(slots=True)
class Write:
    path: str
    kind: str
    bytes: int


class SandboxContext:
    def __init__(
        self,
        *,
        mode: Literal["dry_run", "live"],
        scopes: list[str],
        inputs_dir: Path,
        output_dir: Path,
    ) -> None:
        self.mode = mode
        self.scopes = set(scopes)
        self.inputs_dir = inputs_dir
        self.output_dir = output_dir
        self.intended_writes: list[Write] = []

    def _input_path(self, name: str) -> Path:
        path = (self.inputs_dir / name).resolve()
        if not str(path).startswith(str(self.inputs_dir.resolve())):
            raise PermissionError(f"input path escapes sandbox: {name}")
        if not path.exists():
            # inputs are mounted with the source extension: "file" -> "file.xlsx"
            matches = sorted(self.inputs_dir.glob(f"{glob.escape(name)}.*"))
            if not matches:
                raise FileNotFoundError(name)
            path = matches[0]
        return path

    def read_text(self, name: str) -> str:
        return self._input_path(name).read_text(encoding="utf-8")

    def read_table(self, name: str) -> Any:
        path = self._input_path(name)
        suffix = path.suffix.lower()
        try:
            import pandas as pd  # type: ignore
        except ImportError:
            pd = None

        if pd is not None:
            if suffix in {".xlsx", ".xls"}:
                return pd.read_excel(path)
            return pd.read_csv(path)

        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def fetch(self, url: str) -> str:
        host = (urlparse(url).hostname or "").lower()
        allowed = {sc[4:].lower() for sc in self.scopes if sc.startswith("net:")}
        if not any(host == d or host.endswith("." + d) or d == "*" for d in allowed):
            raise PermissionError(f"network access requires the net:{host} scope")
        recorded = self._fetch_map()
        if recorded is not None:  # replay: recorded pages only, never the live network
            if url not in recorded:
                raise KeyError(f"no recorded page for {url}")
            return recorded[url]
        alias = os.getenv("SANDBOX_LOCALHOST_ALIAS")  # in Docker, "localhost" is the container itself
        if alias and host in {"localhost", "127.0.0.1"}:
            url = url.replace(host, alias, 1)
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.read().decode("utf-8")

    def _fetch_map(self) -> dict[str, str] | None:
        """Gate replay of web tools: input `__fetch_map__` = JSON {url: html} of recorded pages."""
        path = self.inputs_dir / FETCH_MAP_INPUT
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_output(self, name: str, data: Any) -> None:
        path = (self.output_dir / name).resolve()
        if not str(path).startswith(str(self.output_dir.resolve())):
            raise PermissionError(f"output path escapes sandbox: {name}")

        payload = _serialize(data)
        self.intended_writes.append(Write(path=name, kind=_kind_for(name), bytes=len(payload)))
        if self.mode == "dry_run":
            return
        if "write:outputs" not in self.scopes:
            raise PermissionError("writing outputs requires the write:outputs scope")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _serialize(data: Any) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    try:
        import pandas as pd  # type: ignore
    except ImportError:
        pd = None

    if pd is not None and isinstance(data, pd.DataFrame):
        return data.to_csv(index=False).encode("utf-8")
    return json.dumps(data, indent=2, sort_keys=True).encode("utf-8")


def _kind_for(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or "bytes"


def writes_to_dicts(writes: list[Write]) -> list[dict[str, Any]]:
    return [asdict(write) for write in writes]
