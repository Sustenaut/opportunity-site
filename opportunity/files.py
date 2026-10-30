"""Files that go with cards and reports: attachments (photos, figures) and
client documents built from a report. They are kept in storage.sustenaut.eu
(Sustenaut/storage) under the tenant ``opportunity``, never in git.

The storage API (Sustenaut/storage, "general files and kept client documents"):

    POST /opportunity/files        multipart "file", "name", "label", "kept", "for"
                                   -> {id, name, url, type, size, label, kept}
    GET  /opportunity/f/<id>/<name>

A file's id is the SHA-256 of its content, so a new version of a document is
a new file; its ``label`` ("OPP-02 market report v3") says which version it
is. A document that went to a client is uploaded ``kept`` and is never
cleaned up. The site uploads with its GitHub App's installation token and
names the person in ``for``.

TODO(storage): not switched on yet. Storage has no listing, so the site must
record each upload (subject, id, name, label, kept, who) in its own database
and publish the ids it uses at /storage-in-use.json for storage's nightly
clean-up (reachable without the proxy's sign-in). Until that and the storage
deploy are done, ``from_env`` returns None, the pages show the upload button
disabled, and only tests use ``FakeFiles`` and ``StorageClient``.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Protocol

TENANT = "opportunity"
BASE = "https://storage.sustenaut.eu"


@dataclass(frozen=True)
class StoredFile:
    id: str  # the SHA-256 of the content
    subject: str  # the card id or research/<slug>
    name: str
    url: str
    type: str
    size: int
    label: str
    kept: bool  # a client document that went out: never cleaned up
    uploaded_by: str


class Files(Protocol):
    def put(self, subject: str, name: str, data: bytes, uploaded_by: str, *, label: str = "",
            kept: bool = False) -> StoredFile: ...
    def list(self, subject: str) -> list[StoredFile]: ...


class StorageClient:
    """storage.sustenaut.eu, tenant ``opportunity``, with the GitHub App's installation token."""

    def __init__(self, token: Callable[[], str], base_url: str = BASE, tenant: str = TENANT):
        self.token, self.base_url, self.tenant = token, base_url.rstrip("/"), tenant

    def put(self, subject, name, data, uploaded_by, *, label="", kept=False):
        import requests

        r = requests.post(f"{self.base_url}/{self.tenant}/files", timeout=60,
                          headers={"Authorization": f"Bearer {self.token()}"},
                          files={"file": (name, data)},
                          data={"name": name, "label": label, "kept": "true" if kept else "false",
                                "for": uploaded_by})
        if r.status_code != 200:
            raise RuntimeError(f"storage said {r.status_code}: {r.text[:300]}")
        got = r.json()
        return StoredFile(got["id"], subject, got["name"], f"{self.base_url}{got['url']}", got["type"], got["size"],
                          got["label"], got["kept"], uploaded_by)

    def list(self, subject):
        raise NotImplementedError("TODO(storage): the site records its uploads itself; storage has no listing")


class FakeFiles:
    def __init__(self, tenant: str = TENANT):
        self.tenant = tenant
        self.files: dict[tuple[str, str, str], tuple[StoredFile, bytes]] = {}

    def put(self, subject, name, data, uploaded_by, *, label="", kept=False):
        fid = hashlib.sha256(data).hexdigest()
        before = self.files.get((subject, fid, name))
        f = StoredFile(fid, subject, name, f"{BASE}/{self.tenant}/f/{fid}/{name}", "application/octet-stream",
                       len(data), label, kept or bool(before and before[0].kept), uploaded_by)
        self.files[(subject, fid, name)] = (f, data)
        return f

    def list(self, subject):
        return [f for (s, _, _), (f, _) in self.files.items() if s == subject]


def from_env() -> Files | None:
    return None  # TODO(storage): StorageClient(app token) once the steps in the module docstring are done
