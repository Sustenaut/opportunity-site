"""The opportunity site, on a git checkout of fixture cards and a stand-in card format
(fixtures/business-plan/) made in a temporary folder, the in-memory store, and a fake GitHub. The PostgreSQL store runs too
when OPPORTUNITY_TEST_DATABASE_URL names an empty database."""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "business-plan"
sys.path.insert(0, str(ROOT))

from opportunity import access_check, auth, cardformat, content, edits, files, github, main, store  # noqa: E402

ME, CONTROLLER, OTHER = "reviewer@example.org", "owner@example.org", "other@example.org"
ORIGIN = {"origin": "http://testserver"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=t@example.org", "-c", "user.name=t", *args], cwd=repo,
                          check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "business-plan"
    shutil.copytree(FIXTURE, r, ignore=shutil.ignore_patterns("__pycache__"))
    git(r, "init", "-q", "-b", "main")
    commit(r, "cards")
    return r


class FakePublisher:
    def __init__(self):
        self.proposals = []
        self.conflict = False

    def propose(self, *, slug, user, changes, title, body):
        if self.conflict:
            raise github.Conflict("changed on main")
        self.proposals.append({"slug": slug, "user": user, "changes": changes, "title": title, "body": body})
        return f"https://github.com/Sustenaut/business-plan/pull/{100 + len(self.proposals)}"


@pytest.fixture
def site(repo, monkeypatch):
    s = store.MemoryStore()
    pub = FakePublisher()
    shown = content.Content(repo, pull=False)
    shown.now()  # imports the card format, as the first request does
    monkeypatch.setattr(main.Services, "content", shown)
    monkeypatch.setattr(main.Services, "store", s)
    monkeypatch.setattr(main.Services, "publisher", pub)
    monkeypatch.setattr(main.Services, "files", None)
    monkeypatch.setattr(main.Services, "_made", True)
    monkeypatch.setenv("OPPORTUNITY_DEV_USER", ME)
    monkeypatch.delenv("OPPORTUNITY_DEV_GROUPS", raising=False)
    monkeypatch.setattr(auth, "_access", None)
    for v in ("K_SERVICE", "KUBERNETES_SERVICE_HOST"):
        monkeypatch.delenv(v, raising=False)
    return TestClient(main.app), s, pub, repo


def as_user(monkeypatch, email, groups="opportunity"):
    monkeypatch.setenv("OPPORTUNITY_DEV_USER", email)
    monkeypatch.setenv("OPPORTUNITY_DEV_GROUPS", groups)


# --- Reading -----------------------------------------------------------------

def test_index_lists_every_card_ranked_and_filters_by_kind(site):
    client, *_ = site
    page = client.get("/").text
    opp = cardformat.opp()
    cards = [opp.read(p) for p in sorted((FIXTURE / "opportunities").glob("OPP-*.md"))]
    assert all(f"/c/{c['id']}" in page for c in cards)
    assert "Expected levels per 100 h" in page and "Example market report" in page
    best = opp.rows(cards).sort_values("expected levels per 100 h", ascending=False).iloc[0]["id"]
    assert page.index(f"/c/{best}\"") == min(page.index(f"/c/{c['id']}\"") for c in cards)
    platform = client.get("/?kind=platform").text
    assert all((f"/c/{c['id']}\"" in platform) == (c["kind"] == "platform") for c in cards)


def test_card_page_shows_fields_body_and_its_reports(site):
    client, *_ = site
    page = client.get("/c/OPP-01").text
    card = cardformat.opp().read(FIXTURE / "opportunities" / "OPP-01.md")
    assert card["name"] in page and 'data-anchor="f:kill_point"' in page
    assert "/r/example-market" in page  # the report names OPP-01
    assert client.get("/c/OPP-99").status_code == 404
    report = client.get("/r/example-market").text
    assert 'data-anchor="s:verdict"' in report and "/c/OPP-01" in report


def test_card_html_is_shown_as_text_and_script_links_are_dropped():
    out, sections = content.render("## Plan\n\n<script>alert(1)</script> [x](javascript:alert(1)) [ok](https://a.eu)")
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "javascript:" not in out and 'href="https://a.eu"' in out
    assert sections == [("s:plan", "Plan")]


# --- Comments ----------------------------------------------------------------

def test_comment_on_a_field_reply_and_resolve(site, monkeypatch):
    client, s, _, repo = site
    sha = git(repo, "rev-parse", "HEAD")
    r = client.post("/c/OPP-10/comments", data={"anchor": "f:kill_point", "body": "Why March?", "sha": sha},
                    headers=ORIGIN, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/c/OPP-10#c1"
    (c,) = s.comments("OPP-10")
    assert (c.anchor, c.commit_sha, c.author_email, c.parent_id) == ("f:kill_point", sha, ME, None)

    as_user(monkeypatch, OTHER)
    client.post("/c/OPP-10/comments", data={"parent": "1", "body": "The sandbox.", "anchor": "s:x"}, headers=ORIGIN)
    reply = s.comments("OPP-10")[1]
    assert reply.parent_id == 1 and reply.anchor == ""  # a reply is on its thread, not an anchor of its own
    page = client.get("/c/OPP-10").text
    assert "Field: kill_point" in page and "The sandbox." in page and "on an older version" not in page
    assert client.post("/comments/1/resolve", headers=ORIGIN).status_code == 403  # not the author
    assert client.post("/comments/2/resolve", headers=ORIGIN).status_code == 404  # a reply isn't a thread

    as_user(monkeypatch, CONTROLLER, "controller,opportunity")  # a controller may resolve any thread
    assert "· controller" in client.get("/c/OPP-10").text
    assert client.post("/comments/1/resolve", headers=ORIGIN, follow_redirects=False).status_code == 303
    assert s.comment(1).resolved_by == CONTROLLER
    assert main.Services.store.tally().get("OPP-10") is None


def test_author_resolves_own_thread_and_empty_comments_are_refused(site):
    client, s, *_ = site
    assert client.post("/r/example-market/comments", data={"body": "  "}, headers=ORIGIN).status_code == 422
    client.post("/r/example-market/comments", data={"anchor": "s:verdict", "body": "Sizes?"},
                headers=ORIGIN)
    assert s.comments("research/example-market")[0].anchor == "s:verdict"
    client.post("/comments/1/resolve", headers=ORIGIN)
    assert s.comment(1).resolved_by == ME


def test_posts_from_elsewhere_are_refused(site):
    client, s, *_ = site
    assert client.post("/c/OPP-10/comments", data={"body": "hi"}).status_code == 403
    assert client.post("/c/OPP-10/comments", data={"body": "hi"},
                       headers={"origin": "https://evil.example"}).status_code == 403
    assert s.comments("OPP-10") == []


# --- Reviews -----------------------------------------------------------------

def test_reviews_say_when_they_are_on_an_older_version(site):
    client, s, _, repo = site
    first = git(repo, "rev-parse", "HEAD")
    client.post("/c/OPP-10/reviews", data={"verdict": "concerns", "note": "Timing.", "sha": first}, headers=ORIGIN)
    client.post("/r/example-market/reviews", data={"verdict": "reviewed", "sha": first}, headers=ORIGIN)
    assert "on an older version" not in client.get("/c/OPP-10").text

    card = repo / "opportunities" / "OPP-10.md"
    card.write_text(card.read_text() + "\nOne more line.\n")
    commit(repo, "edit OPP-10")
    page = client.get("/c/OPP-10").text
    assert "Reviewed with concerns" in page and "on an older version" in page
    # The report didn't change, so its review is still on the version shown.
    assert "on an older version" not in client.get("/r/example-market").text

    assert client.post("/c/OPP-10/reviews", data={"verdict": "maybe"}, headers=ORIGIN).status_code == 422
    assert client.post("/c/OPP-10/reviews", data={"verdict": "reviewed", "note": "x" * 501},
                       headers=ORIGIN).status_code == 422
    assert [r.verdict for r in s.reviews("OPP-10")] == ["concerns"]


# --- Proposing changes -------------------------------------------------------

def test_front_matter_round_trips_for_every_card(site):
    for p in (FIXTURE / "opportunities").glob("OPP-*.md"):
        text = p.read_text()
        assert edits.join(*edits.split(text)) == text, p.name
        assert edits.edit_card(text, dict(edits.fields_for(text)), edits.split(text)[1]) == text, p.name


def test_an_edit_opens_a_pull_request_naming_the_editor(site):
    client, _, pub, repo = site
    form = {k: v for k, v in [("f:" + k, v) for k, v in edits.fields_for((repo / "opportunities/OPP-10.md").read_text())]}
    form["f:confidence"] = "high (0.85)"
    form["body"] = edits.split((repo / "opportunities/OPP-10.md").read_text())[1]
    form["note"] = "The sandbox replied."
    page = client.post("/c/OPP-10/edit", data=form, headers=ORIGIN)
    assert page.status_code == 200 and "pull/101" in page.text
    (p,) = pub.proposals
    (change,) = p["changes"]
    assert (p["slug"], p["user"], change.path) == ("OPP-10", "reviewer", "opportunities/OPP-10.md")
    assert change.old == (repo / "opportunities/OPP-10.md").read_text()
    assert "confidence: high (0.85)" in change.new and change.new.count("\n") == change.old.count("\n")
    assert "# runs on the shared Hetzner server" in change.new  # comments in other fields stay
    assert ME in p["body"] and "The sandbox replied." in p["body"]


def test_edits_that_do_not_read_cleanly_open_nothing(site):
    client, _, pub, repo = site
    text = (repo / "opportunities/OPP-10.md").read_text()
    body = edits.split(text)[1]
    bad = client.post("/c/OPP-10/edit", data={"f:kill_point": "Stop: no buyers", "body": body}, headers=ORIGIN)
    assert bad.status_code == 422 and "not valid YAML" in bad.text
    assert client.post("/c/OPP-10/edit", data={"f:name": "", "body": body}, headers=ORIGIN).status_code == 422
    same = client.post("/c/OPP-10/edit", data={"body": body}, headers=ORIGIN)
    assert same.status_code == 422 and "Nothing changed" in same.text
    pub.conflict = True
    assert client.post("/c/OPP-10/edit", data={"f:confidence": "low", "body": body}, headers=ORIGIN).status_code == 422
    assert pub.proposals == []
    assert edits.RULE in client.get("/c/OPP-10/edit").text


def test_a_research_report_is_added_by_pull_request(site):
    client, _, pub, _ = site
    form = {"slug": "wallet-relying-parties", "title": "Who pays for wallet sign-in?", "cards": "opp-10, OPP-01",
            "summary": "Buyers of relying-party integration.", "sources": "https://example.org/a\nhttps://example.org/b",
            "body": "## Verdict\n\nSome do."}
    assert client.post("/r/new", data={**form, "cards": "OPP-99"}, headers=ORIGIN).status_code == 422
    assert client.post("/r/new", data={**form, "slug": "example-market"}, headers=ORIGIN).status_code == 422
    assert client.post("/r/new", data={**form, "sources": "not a url"}, headers=ORIGIN).status_code == 422
    assert client.post("/r/new", data=form, headers=ORIGIN).status_code == 200
    (change,) = pub.proposals[0]["changes"]
    assert change.path == "opportunities/research/wallet-relying-parties.md" and change.old is None
    path = Path(main.Services.content.root) / change.path
    path.write_text(change.new)
    report = cardformat.opp().read(path)
    assert report["cards"] == ["OPP-10", "OPP-01"] and report["sources"] and report["warning"] == ""
    assert report["body"].startswith("# Who pays for wallet sign-in?")


def test_branch_names_count_up():
    assert github.branch_name("OPP-10", "david", []) == "opportunity/OPP-10-david-1"
    assert github.branch_name("OPP-10", "david", ["opportunity/OPP-10-david-1", "opportunity/OPP-10-david-7",
                                                  "opportunity/OPP-10-david-x"]) == "opportunity/OPP-10-david-8"


def test_the_github_app_signs_in_and_opens_a_branch_and_pull_request():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from integrations.calls import Caller, MemorySink, Replay

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    api = "https://api.github.com/repos/Sustenaut/business-plan"
    content = base64.b64encode(b"old").decode()
    replay = Replay({
        "POST https://api.github.com/app/installations/456/access_tokens": {"status": 201, "json": {"token": "inst-token"}},
        f"GET {api}/git/ref/heads/main": {"status": 200, "json": {"object": {"sha": "base"}}},
        f"GET {api}/contents/opportunities/OPP-10.md?ref=base": {"status": 200, "json": {"sha": "blob", "content": content}},
        f"GET {api}/git/matching-refs/heads/opportunity/OPP-10-david-": {
            "status": 200, "json": [{"ref": "refs/heads/opportunity/OPP-10-david-1"}]},
        f"POST {api}/git/refs": {"status": 201, "json": {}},
        f"PUT {api}/contents/opportunities/OPP-10.md": {"status": 201, "json": {}},
        f"POST {api}/pulls": {"status": 201, "json": {"html_url": "https://github.com/Sustenaut/business-plan/pull/9"}},
    })
    sink = MemorySink()
    app = github.GitHubApp("123", pem, "456", caller=Caller("opportunity-site", "web", sink=sink, transport=replay))
    with pytest.raises(github.Conflict):
        app.propose(slug="OPP-10", user="david", changes=[github.Change("opportunities/OPP-10.md", "older", "new")],
                    title="t", body="b")
    url = app.propose(slug="OPP-10", user="david", changes=[github.Change("opportunities/OPP-10.md", "old", "new")],
                      title="OPP-10: edit", body="by david")
    assert url.endswith("/pull/9") and app.token() == "inst-token"
    writes = [(r.method, r.url.removeprefix(api), json.loads(r.body)) for r in replay.sent
              if r.method != "GET" and r.url.startswith(api)]
    assert writes[0] == ("POST", "/git/refs", {"ref": "refs/heads/opportunity/OPP-10-david-2", "sha": "base"})
    assert writes[1][:2] == ("PUT", "/contents/opportunities/OPP-10.md") and writes[1][2]["sha"] == "blob"
    assert {r.plugin for r in sink.records} == {"github.app-token", "github.edit-pr"}
    assert {r.repo for r in sink.records} == {"opportunity-site"}


def test_the_call_log_goes_to_storage_only_when_the_deployment_says(monkeypatch, tmp_path):
    monkeypatch.delenv("OPPORTUNITY_CALL_LOG_URL", raising=False)
    github.call_log.cache_clear()
    assert github.call_log() is None
    github.call_log.cache_clear()
    token = tmp_path / "token"
    token.write_text("pod-token\n")
    monkeypatch.setenv("OPPORTUNITY_CALL_LOG_URL", "https://storage.example")
    monkeypatch.setenv("OPPORTUNITY_STORAGE_TOKEN_FILE", str(token))
    monkeypatch.setenv("HOSTNAME", "app-7")
    import integrations.storage_sink as storage_sink
    monkeypatch.setattr(storage_sink, "threading", type("T", (), {"Thread": lambda **kw: type("S", (), {"start": lambda s: None})(),
                                                                  "Lock": __import__("threading").Lock}))
    monkeypatch.setattr(storage_sink.atexit, "register", lambda f: None)
    sink = github.call_log()
    assert github.call_log() is sink
    github.call_log.cache_clear()
    assert isinstance(sink, storage_sink.StorageSink)
    assert sink.datasets == {"opportunity-site": "calls_opportunity_site"} and sink.sender == "app-7"
    assert sink.token() == "pod-token" and sink.base == "https://storage.example"



# --- Content -----------------------------------------------------------------

def test_the_checkout_is_pulled_at_most_once_a_minute(repo, tmp_path):
    clone = tmp_path / "clone"
    c = content.Content(clone, url=str(repo))
    first = c.now().sha
    assert first == git(repo, "rev-parse", "HEAD") and "OPP-10" in c.now().cards
    (repo / "opportunities" / "OPP-10.md").write_text((repo / "opportunities" / "OPP-10.md").read_text() + "\nmore\n")
    second = commit(repo, "edit")
    assert c.now().sha == first  # pulled less than a minute ago
    c.every = 0
    assert c.now().sha == second


def test_the_first_request_clones_even_soon_after_boot(repo, tmp_path, monkeypatch):
    # time.monotonic() counts from boot: on a fresh CI machine it can be under a minute.
    monkeypatch.setattr(content.time, "monotonic", lambda: 5.0)
    c = content.Content(tmp_path / "clone", url=str(repo))
    assert c.now().sha == git(repo, "rev-parse", "HEAD")


def test_a_broken_card_is_reported_not_fatal(repo):
    (repo / "opportunities" / "OPP-98.md").write_text("no front matter\n")
    snap = content.Content(repo, pull=False).now()
    assert "OPP-10" in snap.cards and any("OPP-98.md" in p for p in snap.problems)


def test_the_card_format_comes_from_the_commit_shown(repo, tmp_path):
    c = content.Content(tmp_path / "clone", url=str(repo), every=0)
    assert c.now() and not hasattr(cardformat.opp(), "NEW")
    format_file = repo / "bizplan" / "opportunities.py"
    format_file.write_text(format_file.read_text() + "\nNEW = True\n")
    commit(repo, "the format moves")
    assert c.now() and cardformat.opp().NEW is True


def test_a_broken_format_is_reported_and_the_last_one_stays(repo, tmp_path):
    c = content.Content(tmp_path / "clone", url=str(repo), every=0)
    assert "OPP-10" in c.now().cards
    (repo / "bizplan" / "opportunities.py").write_text("def broken(:\n")
    commit(repo, "broken")
    snap = c.now()
    assert "OPP-10" in snap.cards and any("bizplan.opportunities" in p for p in snap.problems)


def test_without_a_format_the_site_says_so(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(cardformat, "_module", None)
    shutil.rmtree(repo / "bizplan")
    commit(repo, "no format")
    with pytest.raises(ModuleNotFoundError):
        content.Content(repo, pull=False).now()
    with pytest.raises(RuntimeError, match="isn't loaded"):
        cardformat.opp()


# --- Login -------------------------------------------------------------------

class FakeKeycloak(access_check.AccessCheck):
    """The check as it runs, with Keycloak's two answers made up here."""

    def __init__(self):
        super().__init__("https://auth.example/realms/team", "sustenaut.eu", "secret", role="opportunity", hash_ttl=0)
        self.hash, self.roles, self.up, self.userinfo_calls = "one", {}, True, 0

    def _get(self, url, headers):
        if not self.up:
            return 0, {}
        if url.endswith("/access-state"):
            return 200, {"hash": self.hash}
        self.userinfo_calls += 1
        token = headers["Authorization"].removeprefix("Bearer ")
        return (200, {"access": self.roles[token]}) if token in self.roles else (401, {})


def test_the_proxy_login_asks_on_each_request(site, monkeypatch):
    client, *_ = site
    monkeypatch.delenv("OPPORTUNITY_DEV_USER")
    keycloak = FakeKeycloak()
    keycloak.roles = {"me": ["opportunity"], "boss": ["controller", "opportunity"], "other": ["release"]}
    monkeypatch.setattr(auth, "_access", keycloak)

    def get(email, token=None, **kw):
        return client.get("/", headers={"x-forwarded-email": email, **({"x-forwarded-access-token": token} if token else {})},
                          follow_redirects=False, **kw)

    def post(email, token):
        return client.post("/comments/999/resolve", follow_redirects=False,
                           headers={**ORIGIN, "x-forwarded-email": email, "x-forwarded-access-token": token})

    assert client.get("/").status_code == 401
    assert get(OTHER, "other").status_code == 403  # another service's role
    page = get(ME.upper(), "me")
    assert page.status_code == 200 and "· controller" not in page.text
    assert "· controller" in get(CONTROLLER, "boss").text
    assert client.get("/", headers={"x-auth-request-email": ME}).status_code == 401  # passed through by the proxy: never trusted
    # A forged header changes nothing: roles come from userinfo, not from the browser.
    assert "· controller" not in client.get("/", headers={"x-forwarded-email": ME, "x-forwarded-access-token": "me",
                                                          "x-forwarded-groups": "controller,opportunity"}).text

    calls = keycloak.userinfo_calls
    assert get(ME, "me").status_code == 200 and keycloak.userinfo_calls == calls  # nothing changed: no full check

    keycloak.roles["me"], keycloak.hash = ["plan"], "two"  # the role taken away
    assert get(ME, "me").status_code == 403 and keycloak.userinfo_calls == calls + 1
    keycloak.roles["me"], keycloak.hash = ["opportunity"], "three"
    assert get(ME, "me").status_code == 200

    keycloak.up = False  # auth.sustenaut.eu can't be reached: reading goes on, changes don't
    assert get(ME, "me").status_code == 200
    assert post(ME, "me").status_code == 503
    assert get(OTHER, "new").status_code == 503  # nobody to vouch for them
    keycloak.up = True

    del keycloak.roles["me"]  # removed from all: the session has ended
    keycloak.hash = "four"
    gone = get(ME, "me")
    assert gone.status_code == 303 and gone.headers["location"] == "/oauth2/start?rd=/"
    assert post(ME, "me").status_code == 401

    monkeypatch.setenv("OPPORTUNITY_LOGIN", "wallet")  # not built yet: fails closed
    assert get(ME, "me").status_code == 500


def test_the_proxy_login_fails_closed_without_the_client(site, monkeypatch):
    client, *_ = site
    monkeypatch.delenv("OPPORTUNITY_DEV_USER")
    for name in ("OPPORTUNITY_CLIENT_ID", "OPPORTUNITY_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    assert client.get("/", headers={"x-forwarded-email": ME, "x-forwarded-access-token": "me"}).status_code == 500


def test_the_dev_user_is_refused_on_a_cluster(site, monkeypatch):
    client, *_ = site
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    assert client.get("/").status_code == 401


# --- Files -------------------------------------------------------------------

def test_files_wait_for_storage(site, monkeypatch):
    client, *_ = site
    monkeypatch.delenv("OPPORTUNITY_FILES_URL", raising=False)
    assert files.from_env() is None
    assert '<button type="button" disabled>Upload a file</button>' in client.get("/c/OPP-10").text
    fake = files.FakeFiles()
    sent = fake.put("OPP-10", "offer.pdf", b"%PDF-1", ME, label="OPP-10 offer v1", kept=True)
    again = fake.put("OPP-10", "offer.pdf", b"%PDF-1", ME)  # the same file again stays kept
    v2 = fake.put("OPP-10", "offer.pdf", b"%PDF-2", ME, label="OPP-10 offer v2")
    assert again.kept and sent.id != v2.id and len(fake.list("OPP-10")) == 2


def test_with_uploads_on_a_card_has_the_form_and_a_file_goes_to_its_subject(site, monkeypatch):
    client, *_ = site
    fake = files.FakeFiles()
    monkeypatch.setattr(main.Services, "files", fake)
    page = client.get("/c/OPP-10").text
    assert '<form method="post" action="/c/OPP-10/files" enctype="multipart/form-data">' in page
    assert "disabled>Upload a file" not in page
    data = b"%PDF-1.7\r\n\x00\xff binary\r\n--not-a-boundary\r\n"
    answer = client.post("/c/OPP-10/files", headers=ORIGIN, follow_redirects=False,
                         files={"file": ("OPP-10 offer (v1).pdf", data, "application/pdf")},
                         data={"label": " OPP-10 offer v1 ", "kept": "on"})
    assert answer.status_code == 303 and answer.headers["location"] == "/c/OPP-10#files"
    stored, = fake.list("OPP-10")
    assert (stored.name, stored.label, stored.kept, stored.uploaded_by) == ("OPP-10-offer-v1-.pdf", "OPP-10 offer v1", True, ME)
    assert fake.files[("OPP-10", stored.id, stored.name)][1] == data
    shown = client.get("/c/OPP-10").text
    assert "OPP-10-offer-v1-.pdf" in shown and "OPP-10 offer v1" in shown and "kept" in shown


def test_a_stored_file_is_read_through_the_site_as_a_download(site, monkeypatch):
    client, *_ = site
    fake = files.FakeFiles()
    monkeypatch.setattr(main.Services, "files", fake)
    stored = fake.put("OPP-10", "chart.svg", b"<svg onload=alert(1)></svg>", ME)
    page = client.get("/c/OPP-10").text
    assert f'<a href="/files/{stored.id}/chart.svg">chart.svg</a>' in page
    got = client.get(f"/files/{stored.id}/chart.svg")
    assert got.status_code == 200 and got.content == b"<svg onload=alert(1)></svg>"
    assert got.headers["content-disposition"] == 'attachment; filename="chart.svg"'
    assert got.headers["x-content-type-options"] == "nosniff" and got.headers["cache-control"] == "private, no-store"
    for path in (f"/files/{stored.id}/other.svg", "/files/abc/chart.svg", f"/files/{stored.id}/..%2Fx"):
        assert client.get(path).status_code == 404, path

    class Down(files.FakeFiles):
        def get(self, id, name):
            raise files.Unavailable("no answer")

    monkeypatch.setattr(main.Services, "files", Down())
    assert client.get(f"/files/{stored.id}/chart.svg").status_code == 503
    monkeypatch.setattr(main.Services, "files", None)
    assert client.get(f"/files/{stored.id}/chart.svg").status_code == 404


def test_the_client_reads_a_file_with_the_pods_token():
    url = f"GET https://storage.sustenaut.eu/opportunity/f/{'a' * 64}/a.pdf"
    uploads, replay, _ = stored_files({url: {"status": 200, "text": "%PDF"}})
    assert uploads.get("a" * 64, "a.pdf") == b"%PDF"
    assert replay.sent[0].headers["Authorization"] == "Bearer pod-token"
    for answer, error in (({"status": 404, "json": {"error": "not found"}}, LookupError),
                          ({"status": 403, "json": {"error": "no"}}, files.Refused), ({"error": "down"}, files.Unavailable)):
        missing, _, _ = stored_files({url: answer})
        with pytest.raises(error):
            missing.get("a" * 64, "a.pdf")


def test_a_reports_files_are_its_research_subject(site, monkeypatch):
    client, *_ = site
    fake = files.FakeFiles()
    monkeypatch.setattr(main.Services, "files", fake)
    slug = next(iter(main.Services.content.now().reports))
    answer = client.post(f"/r/{slug}/files", headers=ORIGIN, follow_redirects=False,
                         files={"file": ("figure.png", b"\x89PNG", "image/png")})
    assert answer.status_code == 303
    assert [f.kept for f in fake.list(f"research/{slug}")] == [False]


def test_an_upload_without_a_file_or_with_a_long_label_says_so(site, monkeypatch):
    client, *_ = site
    monkeypatch.setattr(main.Services, "files", files.FakeFiles())
    empty = client.post("/c/OPP-10/files", headers=ORIGIN, files={"file": ("", b"", "application/pdf")})
    assert empty.status_code == 422 and "Choose a file to upload." in empty.text
    long = client.post("/c/OPP-10/files", headers=ORIGIN, files={"file": ("a.pdf", b"%PDF", "application/pdf")},
                       data={"label": "x" * 201})
    assert long.status_code == 422 and "under 200 characters" in long.text


def test_storage_refusing_or_down_is_shown_on_the_page(site, monkeypatch):
    client, *_ = site

    class Refusing(files.FakeFiles):
        def put(self, *a, **kw):
            raise files.Refused("opportunity takes pdf, pptx, docx, png, jpg, svg, csv, xlsx, not .exe")

    class Down(files.FakeFiles):
        def put(self, *a, **kw):
            raise files.Unavailable("no answer")

    monkeypatch.setattr(main.Services, "files", Refusing())
    said = client.post("/c/OPP-10/files", headers=ORIGIN, files={"file": ("a.exe", b"MZ", "application/x")})
    assert said.status_code == 422 and "Storage didn&#39;t take it: opportunity takes pdf" in said.text
    monkeypatch.setattr(main.Services, "files", Down())
    down = client.post("/c/OPP-10/files", headers=ORIGIN, files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert down.status_code == 503 and "Try again in a minute" in down.text


def test_uploads_need_storage_switched_on_the_sites_own_page_and_a_form(site, monkeypatch):
    client, *_ = site
    one = {"file": ("a.pdf", b"%PDF", "application/pdf")}
    assert client.post("/c/OPP-10/files", headers=ORIGIN, files=one).status_code == 404
    monkeypatch.setattr(main.Services, "files", files.FakeFiles())
    assert client.post("/c/OPP-10/files", headers={"origin": "https://evil.example"}, files=one).status_code == 403
    assert client.post("/c/OPP-10/files", headers=ORIGIN, data={"label": "x"}).status_code == 415
    assert client.post("/c/NOPE/files", headers=ORIGIN, files=one).status_code == 404
    monkeypatch.setattr(files, "MAX_BYTES", 10)
    big = client.post("/c/OPP-10/files", headers=ORIGIN, files={"file": ("a.pdf", b"x" * (70 * 1024), "application/pdf")})
    assert big.status_code == 413


def test_a_files_name_is_made_one_storage_takes():
    assert files.safe_name("C:\\Users\\me\\Market report (v3).pdf") == "Market-report-v3-.pdf"
    assert files.safe_name("../.hidden.txt") == "file.hidden.txt"
    assert files.safe_name("ü.png") == "file-.png" and files.safe_name("") == "file"
    long = files.safe_name("a" * 300 + ".pdf")
    assert len(long) == 120 and long.endswith(".pdf")


def test_storage_saying_no_or_not_answering_becomes_the_sites_own_errors():
    uploads, _, _ = stored_files({"POST https://storage.sustenaut.eu/opportunity/files":
                                  {"status": 415, "json": {"error": "opportunity takes pdf, not .exe"}}})
    with pytest.raises(files.Refused, match="opportunity takes pdf, not .exe"):
        uploads.put("OPP-10", "a.exe", b"MZ", ME)
    down, _, _ = stored_files({})
    with pytest.raises(files.Unavailable):
        down.put("OPP-10", "a.pdf", b"%PDF", ME)


def stored_files(responses):
    from integrations.calls import Caller, MemorySink, Replay

    sink, replay = MemorySink(), Replay(responses)
    caller = Caller("opportunity-site", "web", sink=sink, transport=replay, sleep=lambda _: None)
    return files.StorageFiles(caller, lambda: "pod-token"), replay, sink


def test_an_upload_goes_to_storage_with_its_card_as_subject():
    import email.parser

    answer = {"id": "f" * 64, "name": "offer.pdf", "url": f"/opportunity/f/{'f' * 64}/offer.pdf",
              "type": "application/pdf", "size": 6, "label": "v1", "subject": "OPP-10", "kept": True}
    uploads, replay, sink = stored_files({"POST https://storage.sustenaut.eu/opportunity/files": {"status": 200, "json": answer}})
    stored = uploads.put("OPP-10", "offer.pdf", b"%PDF-1", ME, label="v1", kept=True)
    sent = replay.sent[0]
    assert sent.method == "POST" and sent.url == "https://storage.sustenaut.eu/opportunity/files"
    assert sent.headers["Authorization"] == "Bearer pod-token"
    form = email.parser.BytesParser().parsebytes(
        f"Content-Type: {sent.headers['Content-Type']}\r\n\r\n".encode() + sent.body)
    got = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in form.get_payload()}
    assert got == {"file": b"%PDF-1", "name": b"offer.pdf", "label": b"v1", "subject": b"OPP-10", "kept": b"true",
                   "for": ME.encode()}
    assert stored == files.StoredFile("f" * 64, "OPP-10", "offer.pdf",
                                      f"https://storage.sustenaut.eu/opportunity/f/{'f' * 64}/offer.pdf",
                                      "application/pdf", 6, "v1", True, ME)
    assert [(r.plugin, r.operation, r.outcome) for r in sink.records] == [("storage.api", "write", "ok")]


def test_a_cards_files_are_the_tenants_listing_for_its_subject():
    def listed(fid, name, **metadata):
        return {"name": name, "id": fid * 64, "url": f"/opportunity/f/{fid * 64}/{name}", "size": 3,
                "uploaded": "2026-11-06T08:00:00.000Z", "metadata": metadata}

    base = "GET https://storage.sustenaut.eu/opportunity/list?prefix=f%2F"
    uploads, replay, _ = stored_files({
        base: {"status": 200, "json": {"files": [
            listed("b", "terms.pdf", subject="OPP-10", label="v2", kept="true", by="k8s:opportunity/app", **{"for": ME}),
            listed("c", "other.pdf", subject="OPP-11", by="k8s:opportunity/app")], "cursor": "2"}},
        f"{base}&cursor=2": {"status": 200, "json": {"files": [
            listed("a", "figure.png", subject="OPP-10", by="k8s:opportunity/app"), listed("d", "old.pdf")], "cursor": None}}})
    found = uploads.list("OPP-10")
    assert [(f.name, f.type, f.label, f.kept, f.uploaded_by) for f in found] == [
        ("figure.png", "image/png", "", False, "k8s:opportunity/app"), ("terms.pdf", "application/pdf", "v2", True, ME)]
    assert found[1].url == f"https://storage.sustenaut.eu/opportunity/f/{'b' * 64}/terms.pdf"
    assert len(replay.sent) == 2 and replay.sent[0].headers["Authorization"] == "Bearer pod-token"


def test_storage_refusing_a_listing_is_an_error_not_an_empty_list():
    from integrations.clients.storage import StorageError

    uploads, _, _ = stored_files({"GET https://storage.sustenaut.eu/opportunity/list?prefix=f%2F":
                                  {"status": 403, "json": {"error": "k8s:x may not read here"}}})
    with pytest.raises(StorageError, match="HTTP 403 k8s:x may not read here"):
        uploads.list("OPP-10")


def test_files_are_on_when_the_deployment_says_where_storage_is(monkeypatch, tmp_path):
    token = tmp_path / "token"
    token.write_text("pod-token\n")
    monkeypatch.setenv("OPPORTUNITY_FILES_URL", "https://storage.example/")
    monkeypatch.setenv("OPPORTUNITY_STORAGE_TOKEN_FILE", str(token))
    monkeypatch.delenv("OPPORTUNITY_CALL_LOG_URL", raising=False)
    github.call_log.cache_clear()
    made = files.from_env()
    assert isinstance(made, files.StorageFiles) and made.base_url == "https://storage.example"
    assert made.storage.tenant == "opportunity" and made.storage._token() == "pod-token"
    assert made.storage.caller.repo == "opportunity-site"


# --- PostgreSQL --------------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("OPPORTUNITY_TEST_DATABASE_URL"),
                    reason="set OPPORTUNITY_TEST_DATABASE_URL to an empty database to test the PostgreSQL store")
def test_postgres_store():
    import psycopg

    url = os.environ["OPPORTUNITY_TEST_DATABASE_URL"]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS comments, reviews, schema_migrations")
    s = store.PostgresStore(url)
    assert s.migrate() == ["001_comments_and_reviews.sql"] and s.migrate() == []
    root = s.add_comment("OPP-10", "f:kill_point", "abc", ME, "Why?")
    reply = s.add_comment("OPP-10", "", "abc", CONTROLLER, "Because.", root.id)
    assert [c.id for c in s.comments("OPP-10")] == [root.id, reply.id] and s.comment(reply.id).parent_id == root.id
    s.add_review("OPP-10", "not-convinced", "", "abc", ME)
    assert s.tally() == {"OPP-10": (1, 1)}
    s.resolve(reply.id, CONTROLLER)  # only a thread's first comment is resolved
    s.resolve(root.id, CONTROLLER)
    assert s.comment(root.id).resolved_by == CONTROLLER and s.comment(reply.id).resolved_by is None
    assert s.tally() == {"OPP-10": (0, 1)} and s.reviews("OPP-10")[0].label == "Not convinced"
    with pytest.raises(psycopg.errors.CheckViolation):
        s.add_review("OPP-10", "maybe", "", "abc", ME)


def test_the_site_is_alive_and_ready_with_its_database():
    http = TestClient(main.app)
    assert http.get("/livez").json() == {"ok": True}
    assert http.get("/healthz").json() == {"ok": True, "unhealthy": []}


def test_a_database_it_cannot_reach_makes_it_unready_but_not_dead(monkeypatch):
    class Down(store.MemoryStore):
        def ping(self):
            raise OSError("connection refused")

    monkeypatch.setattr(main.Services, "store", Down())
    http = TestClient(main.app)
    answer = http.get("/healthz")
    assert answer.status_code == 503 and answer.json() == {"ok": False, "unhealthy": ["opportunity.postgres"]}
    assert http.get("/livez").status_code == 200


def test_a_store_not_made_yet_is_checked_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_DATABASE_URL", "host=127.0.0.1 port=1 dbname=none")
    found = store.check(None)
    assert not found.ok and found.plugin == "opportunity.postgres"
    monkeypatch.delenv("OPPORTUNITY_DATABASE_URL")
    assert store.check(None).ok


def test_the_storage_token_is_read_from_its_file_on_each_upload(tmp_path):
    """The kubelet renews the projected token's file, so each upload reads it afresh."""
    from opportunity import files

    token_file = tmp_path / "token"
    token_file.write_text("first\n")
    token = files.pod_token(str(token_file))
    assert token() == "first"
    token_file.write_text("second")
    assert token() == "second"
