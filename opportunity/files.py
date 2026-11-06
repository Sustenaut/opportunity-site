"""Files that go with cards and reports: attachments (photos, figures) and
client documents built from a report. They are kept in storage.sustenaut.eu
(Sustenaut/storage) under the private tenant ``opportunity``, never in git, and read
and written with integrations' generated storage client (``integrations.clients.storage``).

A file's id is the SHA-256 of its content, so a new version of a document is
a new file; its ``label`` ("OPP-02 market report v3") says which version it
is, and its ``subject`` (the card id, or research/<slug>) which card it goes with. A
card's files are the tenant's listing, filtered by subject, so the site keeps no table of
its uploads. A document that went to a client is uploaded ``kept``. The tenant is
private, so storage never cleans it up, and the site publishes no in-use list.

The site uploads with its pod's service-account token for the audience
storage.sustenaut.eu (the principal ``k8s:opportunity/app``, which the tenant's
``read`` and ``write`` lists name), read from its file on each call, and names the
person in ``for``. Its calls go through the site's ``Caller`` as storage.api, so they
reach its call log.

A card's or report's page has the upload form (``POST /c/<id>/files``,
``/r/<slug>/files``) once ``from_env`` gives a store: when the deployment sets
OPPORTUNITY_FILES_URL. Without it the button stays disabled.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from integrations.calls import Caller

TENANT = "opportunity"
BASE = "https://storage.sustenaut.eu"
MAX_BYTES = 25 * 1024 * 1024  # the opportunity tenant's max_bytes in storage's tenants.json
LABEL_CHARS = 200  # what storage keeps of a label


class Refused(Exception):
    """Storage said no: a type it doesn't take, a file too big, a token it refused."""


class Unavailable(Exception):
    """Storage didn't answer, or failed: another try may work."""


def safe_name(filename: str) -> str:
    """A file's name as storage takes it: letters, digits, dots, dashes and underscores,
    starting with a letter or digit, at most 120, keeping its extension, which says its type."""
    import re

    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", base)
    if not name[:1].isalnum():
        name = "file" + name
    if len(name) > 120:
        stem, dot, ext = name.rpartition(".")
        name = stem[:120 - len(dot + ext)] + dot + ext if dot and len(ext) < 10 else name[:120]
    return name


@dataclass(frozen=True)
class StoredFile:
    id: str  # the SHA-256 of the content
    subject: str  # the card id or research/<slug>
    name: str
    url: str
    type: str
    size: int
    label: str
    kept: bool  # a client document that went out
    uploaded_by: str


class Files(Protocol):
    def put(self, subject: str, name: str, data: bytes, uploaded_by: str, *, label: str = "",
            kept: bool = False) -> StoredFile: ...
    def list(self, subject: str) -> list[StoredFile]: ...
    def get(self, id: str, name: str) -> bytes: ...  # noqa: A002 - storage's name


class StorageFiles:
    """The tenant ``opportunity`` in storage, through integrations' storage client."""

    def __init__(self, caller: Caller, token: Callable[[], str], base_url: str = BASE, tenant: str = TENANT):
        from integrations.clients.storage import Storage

        self.base_url = base_url.rstrip("/")
        self.storage = Storage(caller, tenant, base_url=self.base_url, token=token)

    def put(self, subject, name, data, uploaded_by, *, label="", kept=False):
        from integrations.clients.storage import StorageError, StorageUnavailable

        try:
            got = self.storage.upload_file(data, name=name, label=label or None, subject=subject, kept=kept,
                                           for_=uploaded_by)
        except StorageError as e:
            raise Refused(e.error or f"HTTP {e.status}") from e
        except StorageUnavailable as e:
            raise Unavailable(e.error or e.detail) from e
        return StoredFile(got["id"], subject, got["name"], f"{self.base_url}{got['url']}", got["type"], got["size"],
                          got["label"], got["kept"], uploaded_by)

    def get(self, id, name):  # noqa: A002 - storage's name
        """A stored file's bytes, read with the pod's token: the tenant is private, so a
        browser can't read it from storage itself."""
        from integrations.clients.storage import NotFound, StorageError, StorageUnavailable

        try:
            return self.storage.get_file(id, name)
        except NotFound as e:
            raise LookupError(f"{id}/{name}") from e
        except StorageError as e:
            raise Refused(e.error or f"HTTP {e.status}") from e
        except StorageUnavailable as e:
            raise Unavailable(e.error or e.detail) from e

    def list(self, subject):
        """The subject's files, from every page of the tenant's listing, in name order."""
        found = self.storage.list_files(subject=subject)
        return [StoredFile(f["id"], subject, f["name"], f"{self.base_url}{f['url']}",
                           mimetypes.guess_type(f["name"])[0] or "application/octet-stream", f["size"],
                           f["metadata"].get("label", ""), f["metadata"].get("kept") == "true",
                           f["metadata"].get("for") or f["metadata"].get("by", ""))
                for f in sorted(found, key=lambda f: (f["name"], f["id"]))]


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

    def get(self, id, name):  # noqa: A002
        for (_, fid, fname), (_, data) in self.files.items():
            if (fid, fname) == (id, name):
                return data
        raise LookupError(f"{id}/{name}")


def pod_token(path: str | None = None) -> Callable[[], str]:
    """Reads the projected service-account token afresh on each call: the
    kubelet renews the file before the token expires. Never logged or kept."""
    file = Path(path or os.environ.get("OPPORTUNITY_STORAGE_TOKEN_FILE", "/var/run/secrets/storage.sustenaut.eu/token"))
    return lambda: file.read_text().strip()


def from_env() -> Files | None:
    """Storage, when the deployment says where it is (OPPORTUNITY_FILES_URL); else None,
    and the pages keep the upload button disabled."""
    url = os.environ.get("OPPORTUNITY_FILES_URL")
    if not url:
        return None
    from integrations.calls import Caller

    from .github import APP, call_log

    return StorageFiles(Caller(APP, "web", sink=call_log()), pod_token(), base_url=url)
