"""A stand-in for business-plan's bizplan.opportunities, which the site imports
from its checkout (opportunity/cardformat.py): the same ``FIELDS``, ``read`` and
``rows``, with nothing of the real rules. business-plan's
tests/test_opportunity_contract.py checks the real module against this interface."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

FIELDS = [
    ("id, name", "OPP-nn and a short name", "OPP-10 A short name"),
    ("kind", "income or platform", "platform"),
    ("confidence", "low, medium or high", "medium"),
    ("kill_point", "the test where we stop", "stop if nobody signs up"),
    ("levels", "a made-up score for the matrix", "2"),
    ("hours", "a made-up cost for the matrix", "40"),
]

_CONFIDENCE = {"low": 0.3, "medium": 0.6, "high": 0.85}


def read(path: Path | str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path}: no YAML front matter between --- lines")
    warning = ""
    try:
        card = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        card, warning = {}, "front matter is not valid YAML: quote values that contain \": \""
    return {**card, "file": Path(path).name, "body": m.group(2), "warning": warning}


def rows(cards: list[dict]) -> pd.DataFrame:
    out = []
    for c in cards:
        conf = _CONFIDENCE.get(str(c.get("confidence")).split(" ")[0])
        levels, hours = c.get("levels", 0), c.get("hours")
        out.append({"id": c.get("id"), "way": "", "name": c.get("name", ""), "kind": c.get("kind", ""),
                    "confidence": conf, "MVDS levels": levels,
                    "expected levels per 100 h": levels * conf / hours * 100 if hours and conf is not None else None})
    return pd.DataFrame(out)
