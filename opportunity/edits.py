"""Turning the edit forms into new card and report files, checked before any
pull request is opened.

A card's front matter is edited field by field as text, so a field's YAML
(and its comments) stays as written unless someone changes it. The result
must read back cleanly with ``bizplan.opportunities.read`` and give matrix
rows; a report must name cards that exist and list its sources, as
tests/test_opportunities.py asks.
"""
from __future__ import annotations

import re
import tempfile
from datetime import date
from pathlib import Path

import yaml

from bizplan import opportunities as opp

RULE = ("No dates or build details in opportunity cards: a card says what is true when it is done, "
        "what it costs and what it is worth. When and how it gets built belongs in the plan and in Linear.")
_KEY = re.compile(r"^([A-Za-z_][\w-]*):(?:[ \t]+(.*)|[ \t]*)$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


class Invalid(Exception):
    pass


def hints() -> dict[str, tuple[str, str]]:
    """field -> (what to write, example), from bizplan.opportunities.FIELDS."""
    out = {}
    for names, what, example in opp.FIELDS:
        for name in names.split(", "):
            out[name] = (what, example)
    return out


def split(text: str) -> tuple[list[tuple[str, str]], str]:
    """A card's front matter as (field, value text) in file order, and the body.
    A line before the first field (a comment) is kept under the key "#"."""
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)(.*)$", text, re.S)
    if not m:
        raise Invalid("no YAML front matter between --- lines")
    blocks: list[list[str]] = []
    for line in m.group(1).split("\n"):
        k = _KEY.match(line)
        if k:
            blocks.append([k.group(1), k.group(2) or ""])
        elif blocks:
            blocks[-1][1] += "\n" + line
        else:
            blocks.append(["#", line])
    return [(k, v) for k, v in blocks], m.group(2)


def join(blocks: list[tuple[str, str]], body: str) -> str:
    lines = []
    for key, value in blocks:
        if key == "#":
            lines.append(value)
            continue
        first, _, rest = value.partition("\n")
        lines.append(f"{key}:" + (f" {first}" if first else "") + (f"\n{rest}" if rest else ""))
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def _clean(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").split("\n")).rstrip("\n")


def fields_for(text: str) -> list[tuple[str, str]]:
    """The form's fields: the card's own, then any from FIELDS it doesn't have yet."""
    blocks, _ = split(text)
    have = [(k, v) for k, v in blocks if k != "#"]
    known = {k for k, _ in have}
    return have + [(k, "") for k in hints() if k not in known]


def edit_card(text: str, values: dict[str, str], body: str) -> str:
    """The card with each field set to its form value. An empty value drops a field
    the card didn't have; ``id`` can't change."""
    blocks, old_body = split(text)
    known = {k for k, _ in blocks}
    out = []
    for key, value in blocks:
        if key in values and key not in ("#", "id"):
            value = _clean(values[key])
        out.append((key, value))
    for key in hints():
        if key not in known and _clean(values.get(key, "")):
            out.append((key, _clean(values[key])))
    new_body = body.replace("\r\n", "\n") if body is not None else old_body
    if not new_body.endswith("\n"):
        new_body += "\n"
    return join(out, new_body)


def _read(name: str, text: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / name
        p.write_text(text, encoding="utf-8")
        try:
            return opp.read(p)
        except (ValueError, yaml.YAMLError) as e:
            raise Invalid(str(e).replace(str(p), name))


def check_card(name: str, old: str, new: str) -> dict:
    """The edited card as bizplan reads it; Invalid if it doesn't read cleanly."""
    if new == old:
        raise Invalid("Nothing changed")
    card = _read(name, new)
    if card["warning"]:
        raise Invalid(card["warning"])
    before = _read(name, old)
    if card.get("id") != before.get("id"):
        raise Invalid("A card's id can't change")
    if not card.get("name"):
        raise Invalid("A card needs a name")
    try:
        opp.rows([card])
    except Exception as e:
        raise Invalid(f"The matrix can't read this card: {type(e).__name__}: {e}")
    return card


def new_report(slug: str, title: str, cards: str, summary: str, sources: str, body: str,
               known: set[str], taken: set[str], prepared: date | None = None) -> tuple[str, str]:
    """(path, text) of a new research report; Invalid if anything is missing."""
    slug = slug.strip().lower()
    if not SLUG.match(slug):
        raise Invalid("The file name is lower-case letters, digits and dashes, like example-market")
    if slug in taken or slug == "readme":
        raise Invalid(f"There is already a report called {slug}")
    named = [c for c in re.split(r"[\s,]+", cards.upper()) if c]
    if not named:
        raise Invalid("Name the cards the report informs")
    unknown = sorted(set(named) - known)
    if unknown:
        raise Invalid(f"No such cards: {', '.join(unknown)}")
    urls = [s.strip() for s in sources.splitlines() if s.strip()]
    if not urls or any(not re.match(r"^https?://\S+$", u) for u in urls):
        raise Invalid("List the sources, one web address per line")
    if not title.strip() or not summary.strip() or not body.strip():
        raise Invalid("A report needs a title, a summary and a body")
    front = {"title": title.strip(), "cards": named, "prepared": prepared or date.today(),
             "summary": " ".join(summary.split()), "sources": urls}
    text = body.replace("\r\n", "\n").strip() + "\n"
    if not text.startswith("# "):
        text = f"# {title.strip()}\n\n{text}"
    out = "---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n" + text
    report = _read(f"{slug}.md", out)
    if report["warning"] or report.get("cards") != named:
        raise Invalid(report["warning"] or "The front matter didn't read back as written")
    return f"opportunities/research/{slug}.md", out
