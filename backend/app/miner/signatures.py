"""Canonical actions shared across structured logs, DOM events, and screen labels."""

import json
import logging
from collections.abc import Iterable

from app.config import ROOT

log = logging.getLogger(__name__)
_aliases: dict[str, str] = {}
_unknown: set[str] = set()
_DEFAULT_SHAPES = {
    "table.rename": "cols",
    "table.pivot": "2col",
    "web.fetch": "html",
    "web.extract": "list",
    "web.submit": "form",
    "doc.extract": "params",
    "msg.send": "email",
}


def configure_vocab(items: Iterable[dict]) -> None:
    """Replace the snapshot atomically; candidate verbs never count as known actions."""
    aliases = {}
    for item in items:
        if item["status"] != "active":
            continue
        for alias in [item["_id"], *item.get("aliases", [])]:
            aliases[alias.strip().casefold()] = item["_id"]
    global _aliases
    _aliases = aliases


configure_vocab(json.loads((ROOT / "data/action_vocab_seed.json").read_text()))


def to_signature(verb: str, args_shape: dict) -> str:
    key, _, suffix = verb.strip().casefold().partition(":")
    canonical = _aliases.get(key)
    if canonical is None:
        if key != "other" and key not in _unknown:
            log.warning("Unknown action verb mapped to other")
            if len(_unknown) < 1000:
                _unknown.add(key)
        return "other"
    if canonical in ("file.open", "file.save", "file.download", "file.upload", "doc.read"):
        ext = str(args_shape.get("ext", suffix)).casefold().lstrip(".")
        if key in ("read_excel", "pandas.read_excel"):
            ext = "xlsx"
        elif key in ("read_csv", "pandas.read_csv"):
            ext = "csv"
        return (
            f"{canonical}:{ext}"
            if ext in {"xlsx", "xls", "csv", "pdf", "txt", "html", "json"}
            else canonical
        )
    shape = _DEFAULT_SHAPES.get(canonical)
    return f"{canonical}:{shape}" if shape else canonical
