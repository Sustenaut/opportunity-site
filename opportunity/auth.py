"""Who is reading, set by OPPORTUNITY_LOGIN:

- ``proxy`` (the default, for now): the site sits behind oauth2-proxy, which
  signs people in with Google and passes the email on in X-Forwarded-Email,
  replacing any such header the browser sent. The site trusts that one header
  (OPPORTUNITY_EMAIL_HEADER names another), so it must not be reachable except
  through the proxy. Other headers, such as X-Auth-Request-Email, the proxy
  passes through as the browser sent them, so they are never read. It checks
  the email against TEAM, the
  same comma-separated list review and plan get from Terraform's var.team
  (infra/variables.tf). There is no separate allowlist.
- ``wallet`` (later): the shared sign-in at auth.sustenaut.eu as the OpenID
  Connect client ``opportunity``, the way review-site/review/auth.py does it.
  Not built yet; asking for it fails loudly rather than letting anyone in.

OPPORTUNITY_OWNER (David) may resolve any thread; others resolve their own.
Locally, OPPORTUNITY_DEV_USER stands in for the login; it is refused on a cluster.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, Request

EMAIL_HEADER = "x-forwarded-email"


def on_cluster() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST") or os.environ.get("K_SERVICE"))


@dataclass(frozen=True)
class Person:
    email: str
    login: str  # "proxy" or "dev"

    @property
    def owner(self) -> bool:
        return self.email == os.environ.get("OPPORTUNITY_OWNER", "").strip().lower()

    @property
    def handle(self) -> str:
        """The email's local part, for branch names."""
        return "".join(ch if ch.isalnum() else "-" for ch in self.email.split("@")[0]).strip("-") or "someone"

    def may_resolve(self, author_email: str) -> bool:
        return self.owner or self.email == author_email


def login_mode() -> str:
    mode = os.environ.get("OPPORTUNITY_LOGIN", "proxy")
    if mode == "wallet":
        raise HTTPException(500, "OPPORTUNITY_LOGIN=wallet is not built yet (client 'opportunity' at "
                                 "auth.sustenaut.eu); use proxy")
    if mode != "proxy":
        raise HTTPException(500, f"OPPORTUNITY_LOGIN is proxy (or, later, wallet), not {mode!r}")
    return mode


def team() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("TEAM", "").split(",") if e.strip()}


def person(request: Request) -> Person:
    """The signed-in team member; 401 or 403 otherwise."""
    dev = os.environ.get("OPPORTUNITY_DEV_USER")
    if dev and not on_cluster():
        return Person(dev.strip().lower(), "dev")
    login_mode()
    header = os.environ.get("OPPORTUNITY_EMAIL_HEADER", EMAIL_HEADER)
    email = request.headers.get(header, "").strip().lower()
    if not email:
        raise HTTPException(401, "Sign in through https://opportunity.sustenaut.eu")
    if email not in team():
        raise HTTPException(403, f"{email} isn't on the team list (infra/variables.tf, var.team)")
    return Person(email, "proxy")


def same_origin(request: Request) -> None:
    """A form post must come from the site's own pages, so another site can't post as a
    signed-in browser. Forms have no scripts to add a header, so this checks the
    browser's Origin (or, without one, Referer) against the request's host."""
    host = request.headers.get("host", "")
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if not host or "://" not in origin or origin.split("://", 1)[1].split("/", 1)[0] != host:
        raise HTTPException(403, "Changes are only accepted from the opportunity site's own pages")
