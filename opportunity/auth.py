"""Who is reading, set by OPPORTUNITY_LOGIN:

- ``proxy`` (the default, for now): the site sits behind oauth2-proxy, which
  signs people in with the team realm at auth.sustenaut.eu (a passkey or an
  emailed code) and passes the verified email on in X-Forwarded-Email and the
  access token in X-Forwarded-Access-Token, replacing any such headers the browser
  sent. The site trusts those two (OPPORTUNITY_EMAIL_HEADER names another for the
  email), so it must not be reachable except through the proxy. Other headers, such as
  X-Auth-Request-Email, the proxy passes through as the browser sent them, so they are
  never read. On each request it asks access_check whether the person's access has
  changed: the role opportunity, which the team access page at
  auth.sustenaut.eu/realms/team/access gives. A role taken away or a removal is refused at
  the next request. Nothing runs between requests. If auth.sustenaut.eu can't be reached,
  people go on reading and changes are refused. There is no separate allowlist.
- ``wallet`` (later): the shared sign-in at auth.sustenaut.eu as the OpenID
  Connect client ``opportunity``, the way review-site/review/auth.py does it.
  Not built yet; asking for it fails loudly rather than letting anyone in.

A controller (the role controller) may resolve any thread; others resolve their own.
Locally, OPPORTUNITY_DEV_USER stands in for the login and OPPORTUNITY_DEV_GROUPS for the
roles (default: opportunity); they are refused on a cluster.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import HTTPException, Request

from .access_check import NO_ROLE, SIGN_IN, AccessCheck

EMAIL_HEADER = "x-forwarded-email"
TOKEN_HEADER = "x-forwarded-access-token"
REALM = "https://auth.sustenaut.eu/realms/team"
ROLE = "opportunity"
CONTROLLER = "controller"


def on_cluster() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST") or os.environ.get("K_SERVICE"))


@dataclass(frozen=True)
class Person:
    email: str
    login: str  # "proxy" or "dev"
    groups: frozenset[str] = frozenset()

    @property
    def controller(self) -> bool:
        return CONTROLLER in self.groups

    @property
    def handle(self) -> str:
        """The email's local part, for branch names."""
        return "".join(ch if ch.isalnum() else "-" for ch in self.email.split("@")[0]).strip("-") or "someone"

    def may_resolve(self, author_email: str) -> bool:
        return self.controller or self.email == author_email


def login_mode() -> str:
    mode = os.environ.get("OPPORTUNITY_LOGIN", "proxy")
    if mode == "wallet":
        raise HTTPException(500, "OPPORTUNITY_LOGIN=wallet is not built yet (client 'opportunity' at "
                                 "auth.sustenaut.eu); use proxy")
    if mode != "proxy":
        raise HTTPException(500, f"OPPORTUNITY_LOGIN is proxy (or, later, wallet), not {mode!r}")
    return mode


def groups(value: str) -> frozenset[str]:
    return frozenset(g.strip() for g in value.split(",") if g.strip())


_access: AccessCheck | None = None


def access() -> AccessCheck:
    """The one check of this process, from the sign-in client's id and secret; fails closed without them."""
    global _access
    if _access is None:
        client_id, secret = os.environ.get("OPPORTUNITY_CLIENT_ID"), os.environ.get("OPPORTUNITY_CLIENT_SECRET")
        if not client_id or not secret:
            raise HTTPException(500, "OPPORTUNITY_CLIENT_ID and OPPORTUNITY_CLIENT_SECRET are not set")
        _access = AccessCheck(os.environ.get("OPPORTUNITY_AUTH_REALM", REALM), client_id, secret, role=ROLE)
    return _access


def person(request: Request) -> Person:
    """The signed-in team member; 401 or 403 otherwise."""
    dev = os.environ.get("OPPORTUNITY_DEV_USER")
    if dev and not on_cluster():
        return Person(dev.strip().lower(), "dev", groups(os.environ.get("OPPORTUNITY_DEV_GROUPS", ROLE)))
    login_mode()
    header = os.environ.get("OPPORTUNITY_EMAIL_HEADER", EMAIL_HEADER)
    email = request.headers.get(header, "").strip().lower()
    if not email:
        raise HTTPException(401, "Sign in through https://opportunity.sustenaut.eu")
    write = request.method not in ("GET", "HEAD")
    decision = access().check(email, request.headers.get(TOKEN_HEADER), write=write)
    if decision.allowed:
        return Person(email, "proxy", decision.roles)
    if decision.reason == NO_ROLE:
        raise HTTPException(403, f"{email} doesn't have access to this site; ask a controller "
                                 "(auth.sustenaut.eu/realms/team/access)")
    if decision.reason == SIGN_IN:
        if write:  # the page stays in the browser, with what they typed
            raise HTTPException(401, "Your sign-in has ended. Go back, sign in again in another tab, then send this again.")
        raise HTTPException(303, headers={"Location": "/oauth2/start?rd=" + quote(request.url.path, safe="/")})
    raise HTTPException(503, "The sign-in service can't be reached, so nothing can be changed just now. Go back and "
                             "try again in a moment.")


def same_origin(request: Request) -> None:
    """A form post must come from the site's own pages, so another site can't post as a
    signed-in browser. Forms have no scripts to add a header, so this checks the
    browser's Origin (or, without one, Referer) against the request's host."""
    host = request.headers.get("host", "")
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if not host or "://" not in origin or origin.split("://", 1)[1].split("/", 1)[0] != host:
        raise HTTPException(403, "Changes are only accepted from the opportunity site's own pages")
