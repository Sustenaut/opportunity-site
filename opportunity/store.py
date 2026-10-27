"""Where comments and reviews live: PostgreSQL (OPPORTUNITY_DATABASE_URL).

The schema is the plain SQL in migrations/, applied in name order when the
service starts; schema_migrations remembers which ran. Each comment and
review keeps the commit the page showed, so a later page can say it was made
on an older version.

Locally without a database, and in tests, ``MemoryStore`` stands in.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
VERDICTS = {"reviewed": "Reviewed", "concerns": "Reviewed with concerns", "not-convinced": "Not convinced"}
NOTE_CHARS = 500


@dataclass(frozen=True)
class Comment:
    id: int
    card_or_report: str
    anchor: str
    commit_sha: str
    author_email: str
    body: str
    parent_id: int | None = None
    resolved_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Review:
    id: int
    card_or_report: str
    verdict: str
    note: str
    commit_sha: str
    author_email: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def label(self) -> str:
        return VERDICTS[self.verdict]


class Store(Protocol):
    def comments(self, subject: str) -> list[Comment]: ...
    def comment(self, cid: int) -> Comment | None: ...
    def add_comment(self, subject: str, anchor: str, sha: str, author: str, body: str,
                    parent_id: int | None = None) -> Comment: ...
    def resolve(self, cid: int, by: str) -> None: ...
    def reviews(self, subject: str) -> list[Review]: ...
    def add_review(self, subject: str, verdict: str, note: str, sha: str, author: str) -> Review: ...
    def tally(self) -> dict[str, tuple[int, int]]: ...  # subject -> (open threads, reviews)


class MemoryStore:
    def __init__(self):
        self._comments: dict[int, Comment] = {}
        self._reviews: list[Review] = []

    def comments(self, subject):
        return sorted((c for c in self._comments.values() if c.card_or_report == subject),
                      key=lambda c: (c.created_at, c.id))

    def comment(self, cid):
        return self._comments.get(cid)

    def add_comment(self, subject, anchor, sha, author, body, parent_id=None, created_at=None):
        c = Comment(len(self._comments) + 1, subject, anchor, sha, author, body, parent_id,
                    created_at=created_at or datetime.now(timezone.utc))
        self._comments[c.id] = c
        return c

    def resolve(self, cid, by):
        c = self._comments[cid]
        if c.parent_id is None:
            self._comments[cid] = replace(c, resolved_by=by)

    def reviews(self, subject):
        return [r for r in self._reviews if r.card_or_report == subject]

    def add_review(self, subject, verdict, note, sha, author, created_at=None):
        r = Review(len(self._reviews) + 1, subject, verdict, note, sha, author,
                   created_at or datetime.now(timezone.utc))
        self._reviews.append(r)
        return r

    def tally(self):
        out: dict[str, list[int]] = {}
        for c in self._comments.values():
            if c.parent_id is None and not c.resolved_by:
                out.setdefault(c.card_or_report, [0, 0])[0] += 1
        for r in self._reviews:
            out.setdefault(r.card_or_report, [0, 0])[1] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    def seed(self, path: Path) -> None:
        """Comments and reviews from a fixture file (fixtures/threads.json), for `make opportunity`."""
        data = json.loads(path.read_text())
        for c in data.get("comments", []):
            made = self.add_comment(c["subject"], c.get("anchor", ""), c["sha"], c["author"], c["body"],
                                    c.get("parent"))
            if c.get("resolved_by"):
                self.resolve(made.id, c["resolved_by"])
        for r in data.get("reviews", []):
            self.add_review(r["subject"], r["verdict"], r.get("note", ""), r["sha"], r["author"])


class PostgresStore:
    """One short connection per call: the site is small and quiet."""

    COMMENT = "id, card_or_report, anchor, commit_sha, author_email, body, parent_id, resolved_by, created_at"
    REVIEW = "id, card_or_report, verdict, note, commit_sha, author_email, created_at"

    def __init__(self, url: str):
        self.url = url

    def _connect(self):
        import psycopg

        return psycopg.connect(self.url)

    def migrate(self, folder: Path = MIGRATIONS) -> list[str]:
        """Apply the migrations not yet applied, each in its own transaction; the names applied."""
        applied = []
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                         "(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            conn.commit()
            for f in sorted(folder.glob("*.sql")):
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_xact_lock(hashtext('opportunity-migrations'))")
                    if conn.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (f.name,)).fetchone():
                        continue
                    conn.execute(f.read_text())
                    conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
                    applied.append(f.name)
        return applied

    def comments(self, subject):
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {self.COMMENT} FROM comments WHERE card_or_report = %s "
                                "ORDER BY created_at, id", (subject,)).fetchall()
        return [Comment(*r) for r in rows]

    def comment(self, cid):
        with self._connect() as conn:
            row = conn.execute(f"SELECT {self.COMMENT} FROM comments WHERE id = %s", (cid,)).fetchone()
        return Comment(*row) if row else None

    def add_comment(self, subject, anchor, sha, author, body, parent_id=None):
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO comments (card_or_report, anchor, commit_sha, author_email, body, parent_id) "
                f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING {self.COMMENT}",
                (subject, anchor, sha, author, body, parent_id)).fetchone()
        return Comment(*row)

    def resolve(self, cid, by):
        with self._connect() as conn:
            conn.execute("UPDATE comments SET resolved_by = %s WHERE id = %s AND parent_id IS NULL", (by, cid))

    def reviews(self, subject):
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {self.REVIEW} FROM reviews WHERE card_or_report = %s "
                                "ORDER BY created_at, id", (subject,)).fetchall()
        return [Review(*r) for r in rows]

    def add_review(self, subject, verdict, note, sha, author):
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO reviews (card_or_report, verdict, note, commit_sha, author_email) "
                f"VALUES (%s, %s, %s, %s, %s) RETURNING {self.REVIEW}",
                (subject, verdict, note, sha, author)).fetchone()
        return Review(*row)

    def tally(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT s, sum(t), sum(r) FROM ("
                " SELECT card_or_report s, count(*) t, 0 r FROM comments"
                "  WHERE parent_id IS NULL AND resolved_by IS NULL GROUP BY 1"
                " UNION ALL SELECT card_or_report, 0, count(*) FROM reviews GROUP BY 1) x GROUP BY s").fetchall()
        return {s: (int(t), int(r)) for s, t, r in rows}


def from_env(on_cluster: bool) -> Store:
    url = os.environ.get("OPPORTUNITY_DATABASE_URL")
    if url:
        s = PostgresStore(url)
        s.migrate()
        return s
    if on_cluster:
        raise RuntimeError("OPPORTUNITY_DATABASE_URL is not set")
    s = MemoryStore()  # local only: forgotten when the server stops
    if os.environ.get("OPPORTUNITY_FIXTURES"):
        s.seed(Path(os.environ["OPPORTUNITY_FIXTURES"]))
    return s
