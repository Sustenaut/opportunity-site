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
cleaned up. The site uploads with its pod's service-account token for the
audience storage.sustenaut.eu (the principal ``k8s:opportunity/app``, which
the tenant's ``write`` list names), read from its file on each upload, and
names the person in ``for``. (A GitHub App installation token can't upload:
storage can't tell that it may write.)

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
    """storage.sustenaut.eu, tenant ``opportunity``, with a bearer token from ``token()`` (pod_token)."""

    def __init__(self, token: Callable[[], str], base_url: str = BASE, tenant: str = TENANT, transport=None):
        self.token, self.base_url, self.tenant = token, base_url.rstrip("/"), tenant
        self.transport = transport  # integrations' Network unless a test passes another

    def put(self, subject, name, data, uploaded_by, *, label="", kept=False):
        from integrations.calls import Network, Request

        fields = {"name": name, "label": label, "kept": "true" if kept else "false", "for": uploaded_by}
        body, content_type = multipart(fields, "file", name, data)
        r = (self.transport or Network()).send(Request(
            "POST", f"{self.base_url}/{self.tenant}/files", body=body,
            headers={"Authorization": f"Bearer {self.token()}", "Content-Type": content_type}), 60)
        if r.status != 200:
            raise RuntimeError(f"storage said {r.status or r.error}: {r.body[:300].decode('utf-8', 'replace')}")
        got = r.json()
        return StoredFile(got["id"], subject, got["name"], f"{self.base_url}{got['url']}", got["type"], got["size"],
                          got["label"], got["kept"], uploaded_by)

    def list(self, subject):
        raise NotImplementedError("TODO(storage): the site records its uploads itself; storage has no listing")


def multipart(fields: dict[str, str], file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    """A multipart/form-data body and its Content-Type, so uploads need no HTTP library of their own."""
    import uuid

    boundary = uuid.uuid4().hex

    def quoted(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "")

    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{quoted(k)}"\r\n\r\n{v}\r\n'.encode()
             for k, v in fields.items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{quoted(file_field)}"; '
                 f'filename="{quoted(filename)}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                 + data + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


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


def pod_token(path: str | None = None) -> Callable[[], str]:
    """Reads the projected service-account token afresh on each call: the
    kubelet renews the file before the token expires. Never logged or kept."""
    import os
    from pathlib import Path

    file = Path(path or os.environ.get("OPPORTUNITY_STORAGE_TOKEN_FILE", "/var/run/secrets/storage.sustenaut.eu/token"))
    return lambda: file.read_text().strip()


def from_env() -> Files | None:
    return None  # TODO(storage): StorageClient(pod_token()) once the steps in the module docstring are done
