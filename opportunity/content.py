"""What the site shows: the cards and research reports in a git checkout of
business-plan main.

OPPORTUNITY_REPO_DIR names the checkout. When it is missing and
OPPORTUNITY_REPO_URL is set, the site clones it. It pulls at most once a
minute (OPPORTUNITY_PULL=0 turns pulling off, as `make opportunity` does), and
every page says which commit it shows. The repository is private: on the
cluster, git authenticates with the GitHub App's installation token. The code
that reads the cards comes from that checkout too (cardformat.py).

Comments and reviews keep the commit they were made on; ``current`` tells
whether the card or report has changed since.
"""
from __future__ import annotations

import base64
import html
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from . import cardformat

log = logging.getLogger("uvicorn.error")

PULL_SECONDS = 60
CARDS = "opportunities"
REPORTS = "opportunities/research"
_SAFE_LINK = re.compile(r"^(https?:|mailto:|#|/|\.|[\w-]+[/.#]|[\w-]+$)", re.I)


# --- Markdown ----------------------------------------------------------------

class _SafeLinks(Treeprocessor):
    """Drops links and images whose address is a script (javascript:, data: ...)."""

    def run(self, root):
        for el in root.iter():
            for attr in ("href", "src"):
                if attr in el.attrib and not _SAFE_LINK.match(el.attrib[attr].strip()):
                    del el.attrib[attr]


class _NoRawHtml(Extension):
    """Raw HTML in a card is shown as text, not run: cards come in by pull request,
    and this site renders them to the whole team."""

    def extendMarkdown(self, md):
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(_SafeLinks(md), "safe_links", 0)


def render(body: str) -> tuple[str, list[tuple[str, str]]]:
    """The body as HTML, and its section headings as (anchor, title), anchor ``s:<id>``."""
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc", _NoRawHtml()])
    out = md.convert(body or "")

    def flat(tokens):
        for t in tokens:
            yield f"s:{t['id']}", html.unescape(t["name"])
            yield from flat(t["children"])

    return out, list(flat(md.toc_tokens))


# --- Git ---------------------------------------------------------------------

class Git:
    """git in the checkout, optionally with a token for github.com."""

    def __init__(self, root: Path, token: Callable[[], str] | None = None):
        self.root = root
        self.token = token

    def run(self, *args: str, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
        auth = []
        if self.token:
            basic = base64.b64encode(f"x-access-token:{self.token()}".encode()).decode()
            auth = ["-c", f"http.https://github.com/.extraheader=Authorization: Basic {basic}"]
        # The volume may belong to another user than the server's: trust this checkout only.
        safe = ["-c", f"safe.directory={self.root}"]
        return subprocess.run(["git", *safe, *auth, *args], cwd=cwd or self.root, capture_output=True, text=True,
                              timeout=60, check=check)

    def head(self) -> str:
        return self.run("rev-parse", "HEAD").stdout.strip()

    def last_change(self, path: str) -> str:
        """The commit that last changed the file, or "" if git doesn't know it."""
        out = self.run("log", "-1", "--format=%H", "HEAD", "--", path, check=False)
        return out.stdout.strip()

    def contains(self, sha: str, change: str) -> bool:
        """Whether commit ``sha`` already has ``change`` (``change`` is its ancestor or itself)."""
        if not sha or not change:
            return False
        return self.run("merge-base", "--is-ancestor", change, sha, check=False).returncode == 0


# --- What a page shows -------------------------------------------------------

@dataclass
class Snapshot:
    """The cards and reports at one commit."""

    sha: str
    cards: dict[str, dict]  # by id, as bizplan.opportunities.read gives them, plus "path" and "text"
    reports: dict[str, dict]  # by slug, the same
    problems: list[str] = field(default_factory=list)  # files that couldn't be read
    _rows: list[dict] | None = None

    def rows(self) -> list[dict]:
        """One row per card and way (bizplan.opportunities.rows), plus the card's group."""
        if self._rows is None:
            cards = list(self.cards.values())
            df = cardformat.opp().rows(cards) if cards else None
            records = [] if df is None else df.astype(object).where(df.notna(), None).to_dict("records")
            for r in records:
                r["group"] = self.cards[r["id"]].get("group") or ""
            self._rows = records
        return self._rows

    def reports_for(self, card_id: str) -> list[dict]:
        return [r for r in self.reports.values() if card_id in (r.get("cards") or [])]


def _read_folder(root: Path, folder: str, pattern: str, problems: list[str]) -> list[dict]:
    out = []
    for p in sorted((root / folder).glob(pattern)):
        if p.name == "README.md":
            continue
        try:
            item = cardformat.opp().read(p)
        except Exception as e:  # a broken card must not take the site down
            problems.append(f"{folder}/{p.name}: {e}")
            continue
        item["path"] = f"{folder}/{p.name}"
        item["text"] = p.read_text(encoding="utf-8")
        if item["warning"]:
            problems.append(f"{item['path']}: {item['warning']}")
        out.append(item)
    return out


def snapshot(root: Path, sha: str) -> Snapshot:
    problems: list[str] = []
    try:
        cardformat.load(root, sha)
    except Exception as e:  # a broken commit must not take the site down: read on with the format we have
        if not cardformat.loaded():
            raise
        problems.append(f"{cardformat.MODULE}: {type(e).__name__}: {e}")
    cards = {str(c.get("id")): c for c in _read_folder(root, CARDS, "OPP-*.md", problems)}
    reports = {Path(r["file"]).stem: r for r in _read_folder(root, REPORTS, "*.md", problems)}
    return Snapshot(sha, cards, reports, problems)


class Content:
    """The checkout and what it shows now, pulled at most once every ``every`` seconds."""

    def __init__(self, root: Path, *, url: str | None = None, pull: bool = True,
                 token: Callable[[], str] | None = None, every: float = PULL_SECONDS):
        self.git = Git(root, token)
        self.url, self.pull, self.every = url, pull, every
        self._lock = threading.Lock()
        self._pulled: float | None = None  # when it last pulled; None: not yet
        self._shown: Snapshot | None = None
        self._versions: dict[tuple[str, str, str], bool] = {}

    @property
    def root(self) -> Path:
        return self.git.root

    def now(self) -> Snapshot:
        with self._lock:
            # monotonic() counts from boot, so "never" is None, not 0.
            if self.pull and (self._pulled is None or time.monotonic() - self._pulled >= self.every):
                self._pulled = time.monotonic()
                self._refresh()
            sha = self.git.head()
            if self._shown is None or self._shown.sha != sha:
                self._shown = snapshot(self.root, sha)
            return self._shown

    def _refresh(self) -> None:
        try:
            if not (self.root / ".git").exists():
                if not self.url:
                    raise RuntimeError(f"{self.root} is not a checkout and OPPORTUNITY_REPO_URL is not set")
                self.git.run("clone", "--quiet", "--single-branch", "--branch", "main", self.url, str(self.root),
                             cwd=self.root.parent)
            else:
                self.git.run("pull", "--quiet", "--ff-only")
        except (subprocess.SubprocessError, OSError, RuntimeError) as e:
            # Keep showing what we have; the page's commit says how old it is.
            log.warning("Couldn't pull the opportunities checkout: %s", getattr(e, "stderr", "") or e)

    def current(self, path: str, sha: str | None) -> bool:
        """Whether something made on commit ``sha`` saw the file as it is now."""
        head = self.now().sha
        key = (path, sha or "", head)
        if key not in self._versions:
            self._versions[key] = sha == head or self.git.contains(sha or "", self.git.last_change(path))
        return self._versions[key]


def from_env(token: Callable[[], str] | None = None) -> Content:
    root = Path(os.environ.get("OPPORTUNITY_REPO_DIR", "/data/business-plan")).resolve()
    return Content(root, url=os.environ.get("OPPORTUNITY_REPO_URL"),
                   pull=os.environ.get("OPPORTUNITY_PULL", "1") != "0", token=token)
