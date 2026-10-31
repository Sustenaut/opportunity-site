"""Proposed changes become pull requests in Sustenaut/business-plan.

The site never writes to main. An edit is one commit on a new branch,
``opportunity/<card or report>-<user>-<n>``, and a pull request naming who
made it; the cards change only when someone merges it.

``GitHubApp`` acts as the site's GitHub App (OPPORTUNITY_GITHUB_APP_ID,
OPPORTUNITY_GITHUB_APP_KEY, OPPORTUNITY_GITHUB_INSTALLATION_ID), through the
integrations library's github.app-token and github.edit-pr clients, which make
and record every call. The same token lets git pull the private repository
(content.py). Locally, ``LocalPublisher`` writes the would-be pull request under
build/ instead; tests use a fake.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from integrations.calls import Caller
from integrations.clients.github_app_token import AppToken
from integrations.clients.github_edit_pr import Change, Conflict, EditPullRequests, next_branch

__all__ = ["Change", "Conflict", "GitHubApp", "LocalPublisher", "Publisher", "branch_name", "from_env"]

REPO = "Sustenaut/business-plan"


class Publisher(Protocol):
    def propose(self, *, slug: str, user: str, changes: list[Change], title: str, body: str) -> str:
        """Open a pull request with the changes on a new branch; its URL."""
        ...


def _stem(slug: str, user: str) -> str:
    return f"opportunity/{slug}-{user}-"


def branch_name(slug: str, user: str, taken: list[str]) -> str:
    """opportunity/<slug>-<user>-<n>, with n one past the highest taken."""
    return next_branch(_stem(slug, user), taken)


class GitHubApp:
    def __init__(self, app_id: str, private_key: str, installation_id: str, repo: str = REPO, base: str = "main",
                 caller: Caller | None = None):
        caller = caller or Caller("opportunity-site", "web")
        self.token = AppToken(caller, app_id, private_key, installation_id)
        self.pulls = EditPullRequests(caller, self.token, repo, base)

    def propose(self, *, slug, user, changes, title, body):
        return self.pulls.propose(stem=_stem(slug, user), changes=changes, title=title, body=body)


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
