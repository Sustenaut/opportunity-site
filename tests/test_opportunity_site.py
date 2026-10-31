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

from opportunity import auth, cardformat, content, edits, files, github, main, store  # noqa: E402

ME, OWNER, OTHER = "reviewer@example.org", "owner@example.org", "other@example.org"
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
    monkeypatch.setenv("OPPORTUNITY_OWNER", OWNER)
    for v in ("K_SERVICE", "KUBERNETES_SERVICE_HOST"):
        monkeypatch.delenv(v, raising=False)
    return TestClient(main.app), s, pub, repo


def as_user(monkeypatch, email):
    monkeypatch.setenv("OPPORTUNITY_DEV_USER", email)


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

    as_user(monkeypatch, OWNER)  # the owner may resolve any thread
    assert client.post("/comments/1/resolve", headers=ORIGIN, follow_redirects=False).status_code == 303
    assert s.comment(1).resolved_by == OWNER
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


class Reply:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body

    def raise_for_status(self):
        assert self.status_code < 400


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

def test_the_proxy_login_takes_the_email_header_for_team_members_only(site, monkeypatch):
    client, *_ = site
    monkeypatch.delenv("OPPORTUNITY_DEV_USER")
    monkeypatch.setenv("TEAM", f"{ME}, {OWNER}")
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"x-forwarded-email": OTHER}).status_code == 403
    assert client.get("/", headers={"x-forwarded-email": ME.upper()}).status_code == 200
    # oauth2-proxy passes this one through as the browser sent it: never trusted.
    assert client.get("/", headers={"x-auth-request-email": ME}).status_code == 401
    monkeypatch.setenv("OPPORTUNITY_LOGIN", "wallet")  # not built yet: fails closed
    assert client.get("/", headers={"x-forwarded-email": ME}).status_code == 500


def test_the_dev_user_is_refused_on_a_cluster(site, monkeypatch):
    client, *_ = site
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    assert client.get("/").status_code == 401


# --- Files -------------------------------------------------------------------

def test_files_wait_for_storage(site, monkeypatch):
    client, *_ = site
    assert files.from_env() is None
    assert '<button type="button" disabled>Upload a file</button>' in client.get("/c/OPP-10").text
    fake = files.FakeFiles()
    sent = fake.put("OPP-10", "offer.pdf", b"%PDF-1", ME, label="OPP-10 offer v1", kept=True)
    again = fake.put("OPP-10", "offer.pdf", b"%PDF-1", ME)  # the same file again stays kept
    v2 = fake.put("OPP-10", "offer.pdf", b"%PDF-2", ME, label="OPP-10 offer v2")
    assert again.kept and sent.id != v2.id and len(fake.list("OPP-10")) == 2

    import requests
    seen = {}

    def post(url, **kw):
        seen.update(url=url, **kw)
        return Reply(200, {"id": "f" * 64, "name": "offer.pdf", "url": f"/opportunity/f/{'f' * 64}/offer.pdf",
                           "type": "application/pdf", "size": 6, "label": "v1", "kept": True})
    monkeypatch.setattr(requests, "post", post)
    stored = files.StorageClient(lambda: "ghs_token").put("OPP-10", "offer.pdf", b"%PDF-1", ME, label="v1", kept=True)
    assert seen["url"] == "https://storage.sustenaut.eu/opportunity/files"
    assert seen["headers"]["Authorization"] == "Bearer ghs_token"
    assert seen["data"] == {"name": "offer.pdf", "label": "v1", "kept": "true", "for": ME}
    assert stored.url == f"https://storage.sustenaut.eu/opportunity/f/{'f' * 64}/offer.pdf" and stored.kept


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
    reply = s.add_comment("OPP-10", "", "abc", OWNER, "Because.", root.id)
    assert [c.id for c in s.comments("OPP-10")] == [root.id, reply.id] and s.comment(reply.id).parent_id == root.id
    s.add_review("OPP-10", "not-convinced", "", "abc", ME)
    assert s.tally() == {"OPP-10": (1, 1)}
    s.resolve(reply.id, OWNER)  # only a thread's first comment is resolved
    s.resolve(root.id, OWNER)
    assert s.comment(root.id).resolved_by == OWNER and s.comment(reply.id).resolved_by is None
    assert s.tally() == {"OPP-10": (0, 1)} and s.reviews("OPP-10")[0].label == "Not convinced"
    with pytest.raises(psycopg.errors.CheckViolation):
        s.add_review("OPP-10", "maybe", "", "abc", ME)


def test_the_storage_token_is_read_from_its_file_on_each_upload(tmp_path):
    """The kubelet renews the projected token's file, so each upload reads it afresh."""
    from opportunity import files

    token_file = tmp_path / "token"
    token_file.write_text("first\n")
    token = files.pod_token(str(token_file))
    assert token() == "first"
    token_file.write_text("second")
    assert token() == "second"
