"""Files that go with cards and reports: attachments (photos, figures) and
versioned client documents built from a report. They are kept in
storage.sustenaut.eu (schryer/storage) under the tenant ``opportunity``, never
in git.

TODO(storage): not wired yet. The storage service holds site photos today;
it needs its own pull request first for general files (not only images), a
kept class whose objects are never deleted, and uploads made server-side by a
service like this one. Until then ``from_env`` returns None, the pages show
the upload button disabled, and only tests use ``FakeFiles``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

TENANT = "opportunity"
KINDS = ("attachment", "document")  # a document keeps every version; an attachment is one file


@dataclass(frozen=True)
class StoredFile:
    key: str  # where storage keeps it: <tenant>/<subject>/<name>/v<version>
    subject: str  # the card id or research/<slug>
    name: str
    kind: str
    version: int
    content_type: str
    size: int
    uploaded_by: str
    uploaded_at: datetime


class Files(Protocol):
    def list(self, subject: str) -> list[StoredFile]:
        """The latest version of each file for a card or report."""
        ...

    def versions(self, subject: str, name: str) -> list[StoredFile]: ...
    def put(self, subject: str, name: str, data: bytes, content_type: str, uploaded_by: str,
            kind: str = "attachment") -> StoredFile: ...
    def read(self, key: str) -> bytes: ...


class StorageClient:
    """storage.sustenaut.eu, tenant ``opportunity``. TODO(storage): implement once the
    storage service takes general files server-side (see the module docstring)."""

    def __init__(self, base_url: str = "https://storage.sustenaut.eu", tenant: str = TENANT):
        self.base_url, self.tenant = base_url, tenant

    def _todo(self, *_, **__):
        raise NotImplementedError("storage.sustenaut.eu doesn't take general files yet")

    list = versions = put = read = _todo


class FakeFiles:
    def __init__(self, tenant: str = TENANT):
        self.tenant = tenant
        self._files: list[tuple[StoredFile, bytes]] = []

    def versions(self, subject, name):
        return [f for f, _ in self._files if f.subject == subject and f.name == name]

    def list(self, subject):
        latest: dict[str, StoredFile] = {}
        for f, _ in self._files:
            if f.subject == subject:
                latest[f.name] = f
        return list(latest.values())

    def put(self, subject, name, data, content_type, uploaded_by, kind="attachment"):
        if kind not in KINDS:
            raise ValueError(f"kind is one of {KINDS}")
        before = self.versions(subject, name)
        if before and kind == "attachment":
            raise ValueError(f"{name} is already attached; documents keep versions, attachments don't")
        v = len(before) + 1
        f = StoredFile(f"{self.tenant}/{subject}/{name}/v{v}", subject, name, kind, v, content_type, len(data),
                       uploaded_by, datetime.now(timezone.utc))
        self._files.append((f, data))
        return f

    def read(self, key):
        return next(d for f, d in self._files if f.key == key)


def from_env() -> Files | None:
    return None  # TODO(storage): StorageClient() once storage takes general files
