"""Proposed changes become pull requests in schryer/business-plan.

The site never writes to main. An edit is one commit on a new branch,
``opportunity/<card or report>-<user>-<n>``, and a pull request naming who
made it; the cards change only when someone merges it.

``GitHubApp`` acts as the site's GitHub App: it signs a short JWT with the
app's private key (OPPORTUNITY_GITHUB_APP_ID, OPPORTUNITY_GITHUB_APP_KEY) and
trades it for an installation token (OPPORTUNITY_GITHUB_INSTALLATION_ID). The
same token lets git pull the private repository (content.py). Locally,
``LocalPublisher`` writes the would-be pull request under build/ instead; tests
use a fake.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

API = "https://api.github.com"
REPO = "schryer/business-plan"


@dataclass(frozen=True)
class Change:
    path: str
    old: str | None  # the text the edit started from; None for a new file
    new: str


class Conflict(Exception):
    """The file on main is no longer what the edit started from."""


class Publisher(Protocol):
    def propose(self, *, slug: str, user: str, changes: list[Change], title: str, body: str) -> str:
        """Open a pull request with the changes on a new branch; its URL."""
        ...


def branch_name(slug: str, user: str, taken: list[str]) -> str:
    """opportunity/<slug>-<user>-<n>, with n one past the highest taken."""
    stem = f"opportunity/{slug}-{user}-"
    used = [int(m.group(1)) for t in taken if (m := re.fullmatch(re.escape(stem) + r"(\d+)", t))]
    return f"{stem}{max(used, default=0) + 1}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class GitHubApp:
    def __init__(self, app_id: str, private_key: str, installation_id: str, repo: str = REPO, base: str = "main"):
        self.app_id, self.key, self.installation_id = app_id, private_key, installation_id
        self.repo, self.base = repo, base
        self._token: tuple[str, float] = ("", 0.0)
        self._lock = threading.Lock()

    def _jwt(self) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        now = int(time.time())
        head = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(self.app_id)}).encode())
        key = serialization.load_pem_private_key(self.key.encode(), password=None)
        sig = key.sign(f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{head}.{claims}.{_b64url(sig)}"

    def token(self) -> str:
        """An installation token, reused until a few minutes before it expires."""
        import requests

        with self._lock:
            token, until = self._token
            if time.time() < until:
                return token
            r = requests.post(f"{API}/app/installations/{self.installation_id}/access_tokens", timeout=20,
                              headers={"Authorization": f"Bearer {self._jwt()}",
                                       "Accept": "application/vnd.github+json"})
            r.raise_for_status()
            self._token = (r.json()["token"], time.time() + 45 * 60)  # tokens last an hour
            return self._token[0]

    def _api(self, method: str, path: str, ok=(200, 201), **kw):
        import requests

        r = requests.request(method, f"{API}/repos/{self.repo}{path}", timeout=30, **kw,
                             headers={"Authorization": f"Bearer {self.token()}",
                                      "Accept": "application/vnd.github+json"})
        if r.status_code not in ok:
            raise RuntimeError(f"GitHub {method} {path}: {r.status_code} {r.text[:300]}")
        return r

    def propose(self, *, slug, user, changes, title, body):
        base_sha = self._api("GET", f"/git/ref/heads/{self.base}").json()["object"]["sha"]
        blobs = {}
        for c in changes:
            r = self._api("GET", f"/contents/{c.path}", ok=(200, 404), params={"ref": base_sha})
            now = base64.b64decode(r.json()["content"]).decode() if r.status_code == 200 else None
            if now != c.old:
                raise Conflict(f"{c.path} has changed on main since this page was loaded")
            blobs[c.path] = r.json()["sha"] if r.status_code == 200 else None
        stem = f"heads/opportunity/{slug}-{user}-"
        taken = [ref["ref"].removeprefix("refs/heads/")
                 for ref in self._api("GET", f"/git/matching-refs/{stem}").json()]
        branch = branch_name(slug, user, taken)
        self._api("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
        for c in changes:
            put = {"message": title, "branch": branch, "content": base64.b64encode(c.new.encode()).decode()}
            if blobs[c.path]:
                put["sha"] = blobs[c.path]
            self._api("PUT", f"/contents/{c.path}", json=put)
        pr = self._api("POST", "/pulls", json={"title": title, "head": branch, "base": self.base, "body": body})
        return pr.json()["html_url"]


class LocalPublisher:
    """For `make opportunity`: writes each proposal to <root>/<branch>/ instead of GitHub."""

    def __init__(self, root: Path):
        self.root = root

    def propose(self, *, slug, user, changes, title, body):
        taken = [str(p.relative_to(self.root)) for p in self.root.glob(f"opportunity/{slug}-{user}-*")]
        branch = branch_name(slug, user, taken)
        out = self.root / branch
        for c in changes:
            (out / c.path).parent.mkdir(parents=True, exist_ok=True)
            (out / c.path).write_text(c.new, encoding="utf-8")
        (out / "PULL_REQUEST.md").write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        return out.resolve().as_uri()


def from_env(on_cluster: bool) -> Publisher:
    app_id = os.environ.get("OPPORTUNITY_GITHUB_APP_ID")
    if app_id:
        return GitHubApp(app_id, os.environ["OPPORTUNITY_GITHUB_APP_KEY"],
                         os.environ["OPPORTUNITY_GITHUB_INSTALLATION_ID"],
                         os.environ.get("OPPORTUNITY_GITHUB_REPO", REPO))
    if on_cluster:
        raise RuntimeError("OPPORTUNITY_GITHUB_APP_ID is not set")
    return LocalPublisher(Path(os.environ.get("OPPORTUNITY_PROPOSALS_DIR", "build/opportunity-proposals")))
