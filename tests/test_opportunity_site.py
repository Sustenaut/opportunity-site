"""The opportunity site, on a git checkout of fixture cards and a stand-in card format
(fixtures/business-plan/) made in the scratch directory, the in-memory store, and a fake GitHub;
read and posted to with pubtest's HTTP steps. The PostgreSQL store runs too when
OPPORTUNITY_TEST_DATABASE_URL names an empty database."""
from __future__ import annotations

import base64
import email.parser
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pubtest.core import show
from pubtest.http import Answer
from pubtest.steps.http import send
from pytest_bdd import given, parsers, scenarios, then, when

FEATURES = Path(__file__).resolve().parent / "features"
scenarios(*(str(FEATURES / name) for name in (
    "opportunity-site.feature", "proposals.feature", "login.feature", "checkout.feature", "files.feature", "storage.feature", "health.feature")))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opportunity import access_check, auth, cardformat, content, edits, files, github, main, store  # noqa: E402


@pytest.fixture
def http_client():
    """The site, as a browser reaches it at http://testserver: redirects are not followed."""
    client = TestClient(main.app)

    def answer(method, path, headers, body):
        got = client.request(method, path, headers=headers, content=body, follow_redirects=False)
        return Answer(got.status_code, dict(got.headers), got.content)

    return answer


def head(ctx) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ctx.directory, capture_output=True, text=True,
                          check=True).stdout.strip()


class FakePublisher:
    def __init__(self):
        self.proposals = []
        self.conflict = False

    def propose(self, *, slug, user, changes, title, body):
        if self.conflict:
            raise github.Conflict("changed on main")
        self.proposals.append({"slug": slug, "user": user, "changes": changes, "title": title, "body": body})
        return f"https://github.com/Sustenaut/business-plan/pull/{100 + len(self.proposals)}"


# --- The site ----------------------------------------------------------------

@given("the site shows this checkout, on a laptop")
def site(ctx, monkeypatch):
    ctx.store, ctx.publisher = store.MemoryStore(), FakePublisher()
    shown = content.Content(ctx.directory, pull=False)
    shown.now()  # imports the card format, as the first request does
    monkeypatch.setattr(main.Services, "content", shown)
    monkeypatch.setattr(main.Services, "store", ctx.store)
    monkeypatch.setattr(main.Services, "publisher", ctx.publisher)
    monkeypatch.setattr(main.Services, "files", None)
    monkeypatch.setattr(main.Services, "_made", True)
    monkeypatch.delenv("OPPORTUNITY_DEV_GROUPS", raising=False)
    monkeypatch.setattr(auth, "_access", None)
    for name in ("K_SERVICE", "KUBERNETES_SERVICE_HOST"):
        monkeypatch.delenv(name, raising=False)


@given(parsers.parse('"{author}" commented "{text}" on "{anchor}" of "{subject}"'))
def commented(ctx, author, text, anchor, subject):
    ctx.store.add_comment(subject, anchor, head(ctx), author, text)


@given(parsers.parse('"{author}" replied "{text}" to thread {thread:d}'))
def replied(ctx, author, text, thread):
    ctx.store.add_comment(ctx.store.comment(thread).card_or_report, "", head(ctx), author, text, thread)


@given(parsers.parse('"{author}" resolved thread {thread:d}'))
def resolved(ctx, author, thread):
    ctx.store.resolve(thread, author)


@given(parsers.parse('"{author}" reviewed "{subject}" as "{verdict}", on the commit shown'))
def reviewed(ctx, author, subject, verdict):
    ctx.store.add_review(subject, verdict, "", head(ctx), author)


@given(parsers.parse('"{author}" reviewed "{subject}" as "{verdict}", saying "{note}", on the commit shown'))
def reviewed_saying(ctx, author, subject, verdict, note):
    ctx.store.add_review(subject, verdict, note, head(ctx), author)


@given("someone has changed the card on main since")
def conflict(ctx):
    ctx.publisher.conflict = True


def _form_send(ctx, http_client, path, fields: dict) -> None:
    from urllib.parse import urlencode
    send(ctx, http_client, "POST", path, urlencode(fields).encode(), "application/x-www-form-urlencoded")


@when(parsers.parse('I comment "{text}" on "{anchor}" of "{path}", on the commit shown'))
def comment(ctx, http_client, text, anchor, path):
    _form_send(ctx, http_client, path, {"anchor": anchor, "body": text, "sha": head(ctx)})


@when(parsers.parse('I review "{path}" as "{verdict}", on the commit shown'))
def review(ctx, http_client, path, verdict):
    _form_send(ctx, http_client, path, {"verdict": verdict, "sha": head(ctx)})


@when(parsers.parse('I review "{path}" as "{verdict}", with a note of {count:d} characters'))
def review_long(ctx, http_client, path, verdict, count):
    _form_send(ctx, http_client, path, {"verdict": verdict, "note": "x" * count})


@when(parsers.parse('the comments on "{subject}" are read'))
def comments_read(ctx, subject):
    shown = head(ctx)

    def rows():
        return [{"id": c.id, "anchor": c.anchor, "commit": "shown" if c.commit_sha == shown else c.commit_sha,
                 "author_email": c.author_email, "parent_id": c.parent_id, "resolved_by": c.resolved_by}
                for c in ctx.store.comments(subject)]
    ctx.attempt(rows)


@when(parsers.parse('the reviews on "{subject}" are read'))
def reviews_read(ctx, subject):
    ctx.attempt(lambda: [{"verdict": r.verdict, "note": r.note, "author_email": r.author_email}
                         for r in ctx.store.reviews(subject)])


@when("the open threads and reviews are counted")
def tally(ctx):
    ctx.attempt(lambda: {k: list(v) for k, v in main.Services.store.tally().items()})


@when("the Markdown is rendered:")
def rendered(ctx, docstring):
    ctx.attempt(lambda: content.render(docstring)[0])


@when("the Markdown's sections are listed:")
def sections(ctx, docstring):
    ctx.attempt(lambda: [list(s) for s in content.render(docstring)[1]])


# --- Proposals ---------------------------------------------------------------

def _card_text(ctx, card):
    return (ctx.directory / "opportunities" / f"{card}.md").read_text()


@when(parsers.parse('I propose an edit to "{card}" with every field, changing:'))
def propose_every(ctx, http_client, card, datatable):
    text = _card_text(ctx, card)
    form = {"f:" + k: v for k, v in edits.fields_for(text)}
    form["body"] = edits.split(text)[1]
    for name, text in datatable[1:]:
        form[name] = text
    _form_send(ctx, http_client, f"/c/{card}/edit", form)


@when(parsers.parse('I propose an edit to "{card}" with only:'))
def propose_only(ctx, http_client, card, datatable):
    form = {"body": edits.split(_card_text(ctx, card))[1]}
    for name, text in datatable[1:]:
        form[name] = text
    _form_send(ctx, http_client, f"/c/{card}/edit", form)


@when("I propose the research report:")
def propose_report(ctx, http_client, datatable):
    _form_send(ctx, http_client, "/r/new", {name: text.replace("\\n", "\n") for name, text in datatable[1:]})


@when("the pull requests proposed are read")
def proposals_read(ctx):
    ctx.attempt(lambda: [{**p, "changes": [{"path": c.path, "old": c.old, "new": c.new} for c in p["changes"]]}
                         for p in ctx.publisher.proposals])


@when("the card the pull request proposes is read")
def proposal_new(ctx):
    ctx.attempt(lambda: ctx.publisher.proposals[0]["changes"][0].new)


@when("the card the pull request started from is read")
def proposal_old(ctx):
    ctx.attempt(lambda: ctx.publisher.proposals[0]["changes"][0].old)


@when("the body of the pull request proposed is read")
def proposal_body(ctx):
    ctx.attempt(lambda: ctx.publisher.proposals[0]["body"])


@when("the report proposed is read through the card format")
def report_read(ctx):
    def read():
        (change,) = ctx.publisher.proposals[0]["changes"]
        path = Path(main.Services.content.root) / change.path
        path.write_text(change.new)
        report = cardformat.opp().read(path)
        return {"cards": report["cards"], "sources": report["sources"], "warning": report["warning"] or None,
                "first line": report["body"].splitlines()[0]}
    ctx.attempt(read)


@when(parsers.parse('every card\'s front matter is split and joined again'))
def round_trip(ctx):
    def trips():
        out = {}
        for p in sorted((ctx.directory / "opportunities").glob("OPP-*.md")):
            text = p.read_text()
            out[p.stem] = {"joined": edits.join(*edits.split(text)) == text,
                           "edited": edits.edit_card(text, dict(edits.fields_for(text)), edits.split(text)[1]) == text}
        return out
    ctx.attempt(trips)


@when(parsers.parse('a branch name is made for "{slug}" by "{user}", with the branches "{taken}"'))
def branch_name(ctx, slug, user, taken):
    ctx.attempt(lambda: github.branch_name(slug, user, json.loads(taken)))


# --- The GitHub App ----------------------------------------------------------

API = "https://api.github.com/repos/Sustenaut/business-plan"


@given("the GitHub App on recorded answers, with OPP-10 holding \"old\" on main")
def github_app(ctx):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from integrations.calls import Caller, MemorySink, Replay

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    ctx.replay = Replay({
        "POST https://api.github.com/app/installations/456/access_tokens": {"status": 201, "json": {"token": "inst-token"}},
        f"GET {API}/git/ref/heads/main": {"status": 200, "json": {"object": {"sha": "base"}}},
        f"GET {API}/contents/opportunities/OPP-10.md?ref=base": {
            "status": 200, "json": {"sha": "blob", "content": base64.b64encode(b"old").decode()}},
        f"GET {API}/git/matching-refs/heads/opportunity/OPP-10-david-": {
            "status": 200, "json": [{"ref": "refs/heads/opportunity/OPP-10-david-1"}]},
        f"POST {API}/git/refs": {"status": 201, "json": {}},
        f"PUT {API}/contents/opportunities/OPP-10.md": {"status": 201, "json": {}},
        f"POST {API}/pulls": {"status": 201, "json": {"html_url": "https://github.com/Sustenaut/business-plan/pull/9"}},
    })
    ctx.sink = MemorySink()
    ctx.app = github.GitHubApp("123", pem, "456", caller=Caller("opportunity-site", "web", sink=ctx.sink,
                                                                     transport=ctx.replay))


@when(parsers.parse('the app proposes OPP-10 by "{user}", from "{old}" to "{new}"'))
def app_proposes(ctx, user, old, new):
    ctx.attempt(lambda: ctx.app.propose(slug="OPP-10", user=user, changes=[
        github.Change("opportunities/OPP-10.md", old, new)], title="OPP-10: edit", body=f"by {user}"))


@when("what the app wrote to GitHub and logged is read")
def app_record(ctx):
    def record():
        writes = [{"method": r.method, "path": r.url.removeprefix(API), "body": json.loads(r.body)}
                  for r in ctx.replay.sent if r.method != "GET" and r.url.startswith(API)]
        return {"writes": writes, "token": ctx.app.token(), "plugins": sorted({r.plugin for r in ctx.sink.records}),
                "repos": sorted({r.repo for r in ctx.sink.records})}
    ctx.attempt(record)


@given("the storage sink's reports don't start")
def sink_quiet(monkeypatch):
    import threading

    import integrations.storage_sink as storage_sink
    monkeypatch.setattr(storage_sink, "threading", type("T", (), {
        "Thread": lambda **kw: type("S", (), {"start": lambda s: None})(), "Lock": threading.Lock}))
    monkeypatch.setattr(storage_sink.atexit, "register", lambda f: None)


@when("the call log is made from the environment")
def call_log(ctx):
    def made():
        github.call_log.cache_clear()
        try:
            sink = github.call_log()
            if sink is None:
                return None
            return {"class": type(sink).__name__, "made once": github.call_log() is sink, "datasets": sink.datasets,
                    "sender": sink.sender, "token": sink.token(), "base": sink.base}
        finally:
            github.call_log.cache_clear()
    ctx.attempt(made)


# --- The checkout ------------------------------------------------------------

@given("a clone of this checkout, pulled at most once a minute")
def clone(ctx, tmp_path):
    ctx.clone = content.Content(tmp_path / "clone", url=str(ctx.directory))


@given("a clone of this checkout, pulled on each read")
def clone_each(ctx, tmp_path):
    ctx.clone = content.Content(tmp_path / "clone", url=str(ctx.directory), every=0)


@given("the clone was read")
def clone_read_once(ctx):
    ctx.first = ctx.clone.now().sha


@given("the clone pulls on each read from now on")
def clone_every(ctx):
    ctx.clone.every = 0


@given("the machine booted five seconds ago")
def booted(monkeypatch):
    # time.monotonic() counts from boot: on a fresh CI machine it can be under a minute.
    monkeypatch.setattr(content.time, "monotonic", lambda: 5.0)


@given(parsers.parse('the card format gains "{line}"'))
def format_gains(ctx, line):
    path = ctx.directory / "bizplan" / "opportunities.py"
    path.write_text(path.read_text() + f"\n{line}\n")


@given("no card format was loaded yet")
def no_format(monkeypatch):
    monkeypatch.setattr(cardformat, "_module", None)


def _shown(ctx, snap):
    return {"commit": "latest" if snap.sha == head(ctx) else
            "first" if snap.sha == getattr(ctx, "first", None) else snap.sha,
            "cards": sorted(snap.cards), "problems": [p.replace(f"{ctx.directory}/", "") for p in snap.problems],
            "NEW": getattr(cardformat.opp(), "NEW", None)}


@when("the clone is read")
def clone_read(ctx):
    ctx.attempt(lambda: _shown(ctx, ctx.clone.now()))


@when("the checkout is read")
def checkout_read(ctx):
    ctx.attempt(lambda: _shown(ctx, content.Content(ctx.directory, pull=False).now()))


@when("the card format is asked for")
def format_asked(ctx):
    ctx.attempt(cardformat.opp)


# --- Login -------------------------------------------------------------------

@given(parsers.parse('the team realm is the fake "{name}" service, asked on each request'))
def realm(ctx, monkeypatch, name):
    from pubtest.steps.fakes import fake
    found = fake(ctx, monkeypatch, name)
    monkeypatch.setattr(auth, "_access", access_check.AccessCheck(
        f"{found.url}/realms/team", "sustenaut.eu", "secret", role="opportunity", hash_ttl=0))


@given("the site's access check is not made yet")
def no_access_check(monkeypatch):
    monkeypatch.setattr(auth, "_access", None)


# --- Files -------------------------------------------------------------------

@given("the site's uploads are fake files")
def fake_files(ctx, monkeypatch):
    ctx.files = files.FakeFiles()
    monkeypatch.setattr(main.Services, "files", ctx.files)


@given(parsers.parse('the fake files hold "{name}" for "{subject}", holding "{text}"'))
def fake_holds(ctx, name, subject, text):
    ctx.files.put(subject, name, text.encode(), "reviewer@example.org")


@given(parsers.parse('the site\'s uploads refuse, saying "{reason}"'))
def uploads_refuse(monkeypatch, reason):
    class Refusing(files.FakeFiles):
        def put(self, *a, **kw):
            raise files.Refused(reason)
    monkeypatch.setattr(main.Services, "files", Refusing())


@given("the site's uploads don't answer")
def uploads_down(monkeypatch):
    class Down(files.FakeFiles):
        def put(self, *a, **kw):
            raise files.Unavailable("no answer")

        def get(self, id, name):  # noqa: A002
            raise files.Unavailable("no answer")
    monkeypatch.setattr(main.Services, "files", Down())


@given("the site's uploads are switched off")
def uploads_off(monkeypatch):
    monkeypatch.setattr(main.Services, "files", None)


@given(parsers.parse("the site takes files of at most {count:d} bytes"))
def max_bytes(monkeypatch, count):
    monkeypatch.setattr(files, "MAX_BYTES", count)


STRAY = b"%PDF-1.7\r\n\x00\xff binary\r\n--not-a-boundary\r\n"


@given(parsers.parse('a file "{path}" of binary bytes and a stray multipart boundary'))
def binary_file(ctx, path):
    (ctx.directory / path).write_bytes(STRAY)


@given(parsers.parse('a file "{path}" of {count:d} bytes'))
def big_file(ctx, path, count):
    (ctx.directory / path).write_bytes(b"x" * count)


def _multipart(fields: dict[str, tuple[str | None, bytes, str | None]]) -> tuple[bytes, str]:
    boundary = "pubtest-boundary-7f3e"
    body = b""
    for name, (filename, data, kind) in fields.items():
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename is not None else "")
        body += f"--{boundary}\r\nContent-Disposition: {disposition}\r\n".encode()
        if kind:
            body += f"Content-Type: {kind}\r\n".encode()
        body += b"\r\n" + data + b"\r\n"
    return body + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def _upload(ctx, http_client, path, filename, kind, data, extra):
    fields = {"file": (filename, data, kind)}
    for name, text in extra:
        fields[name] = (None, text.encode(), None)
    body, content_type = _multipart(fields)
    send(ctx, http_client, "POST", path, body, content_type)


@when(parsers.parse('I upload "{file}" to "{path}" as "{filename}" of type "{kind}"'))
def upload(ctx, http_client, file, path, filename, kind):
    _upload(ctx, http_client, path, filename, kind, (ctx.directory / file).read_bytes(), [])


@when(parsers.parse('I upload "{file}" to "{path}" as "{filename}" of type "{kind}", with:'))
def upload_with(ctx, http_client, file, path, filename, kind, datatable):
    _upload(ctx, http_client, path, filename, kind, (ctx.directory / file).read_bytes(), datatable[1:])


@when(parsers.parse('I upload "{file}" to "{path}" as "{filename}" of type "{kind}", labelled with {count:d} characters'))
def upload_long_label(ctx, http_client, file, path, filename, kind, count):
    _upload(ctx, http_client, path, filename, kind, (ctx.directory / file).read_bytes(), [("label", "x" * count)])


@when(parsers.parse('I upload no file to "{path}"'))
def upload_nothing(ctx, http_client, path):
    _upload(ctx, http_client, path, "", "application/pdf", b"", [])


@when(parsers.parse('the files on "{subject}" are read'))
def files_read(ctx, subject):
    ctx.attempt(lambda: [{"name": f.name, "label": f.label, "kept": f.kept, "uploaded_by": f.uploaded_by,
                          "sha256": hashlib.sha256(ctx.files.files[(subject, f.id, f.name)][1]).hexdigest()}
                         for f in ctx.files.list(subject)])


@when(parsers.parse('"{name}" is put in the fake files three times: as sent, again, and changed'))
def fake_three(ctx, name):
    def put():
        fake = files.FakeFiles()
        sent = fake.put("OPP-10", name, b"%PDF-1", "reviewer@example.org", label="OPP-10 offer v1", kept=True)
        again = fake.put("OPP-10", name, b"%PDF-1", "reviewer@example.org")  # the same file again stays kept
        changed = fake.put("OPP-10", name, b"%PDF-2", "reviewer@example.org", label="OPP-10 offer v2")
        return {"again kept": again.kept, "a new id for the change": sent.id != changed.id,
                "listed": len(fake.list("OPP-10"))}
    ctx.attempt(put)


@when("the site's files are made from the environment")
def files_from_env(ctx):
    def made():
        github.call_log.cache_clear()
        found = files.from_env()
        if found is None:
            return None
        return {"class": type(found).__name__, "base_url": found.base_url, "tenant": found.storage.tenant,
                "token": found.storage._token(), "repo": found.storage.caller.repo}
    ctx.attempt(made)


@when(parsers.parse('the file name "{name}" is made one storage takes'))
def safe_name(ctx, name):
    ctx.attempt(lambda: files.safe_name(name))


@when(parsers.parse("a file name of {count:d} letters and .pdf is made one storage takes"))
def safe_long_name(ctx, count):
    ctx.attempt(lambda: files.safe_name("a" * count + ".pdf"))


@when("no file name is made one storage takes")
def safe_empty_name(ctx):
    ctx.attempt(lambda: files.safe_name(""))


# --- Storage, through integrations' client on recorded answers ---------------

@given("storage on recorded answers:")
def storage_answers(ctx, docstring):
    from integrations.calls import Caller, MemorySink, Replay

    ctx.sink, ctx.replay = MemorySink(), Replay(json.loads(docstring))
    caller = Caller("opportunity-site", "web", sink=ctx.sink, transport=ctx.replay, sleep=lambda _: None)
    ctx.storage = files.StorageFiles(caller, lambda: "pod-token")


@when(parsers.parse('the file "{fid}" named "{name}" is read from storage'))
def storage_get(ctx, fid, name):
    ctx.attempt(lambda: ctx.storage.get(fid, name).decode())


@when(parsers.parse('"{name}" holding "{text}" is put in storage for "{subject}", by "{by}"'))
def storage_put(ctx, name, text, subject, by):
    ctx.attempt(lambda: ctx.storage.put(subject, name, text.encode(), by))


@when(parsers.parse('"{name}" holding "{text}" is put in storage for "{subject}", by "{by}", labelled "{label}" and kept'))
def storage_put_kept(ctx, name, text, subject, by, label):
    ctx.attempt(lambda: ctx.storage.put(subject, name, text.encode(), by, label=label, kept=True))


@when(parsers.parse('the files on "{subject}" are listed from storage'))
def storage_list(ctx, subject):
    ctx.attempt(lambda: [{"name": f.name, "type": f.type, "label": f.label, "kept": f.kept,
                          "uploaded_by": f.uploaded_by, "url": f.url} for f in ctx.storage.list(subject)])


@when("what was sent to storage and logged is read")
def storage_sent(ctx):
    def sent():
        out = []
        for r in ctx.replay.sent:
            entry = {"method": r.method, "url": r.url, "authorization": r.headers.get("Authorization")}
            if r.body and r.headers.get("Content-Type", "").startswith("multipart/"):
                form = email.parser.BytesParser().parsebytes(
                    f"Content-Type: {r.headers['Content-Type']}\r\n\r\n".encode() + r.body)
                entry["form"] = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True).decode()
                                 for p in form.get_payload()}
            out.append(entry)
        return {"sent": out, "requests": len(out), "records": [[r.plugin, r.operation, r.outcome] for r in ctx.sink.records]}
    ctx.attempt(sent)


@given("the storage token was read from its file")
def token_read_before(ctx):
    """The kubelet renews the projected token's file, so each upload reads it afresh."""
    ctx.token = files.pod_token(str(ctx.directory / "token"))
    ctx.token()


@when("the storage token is read from its file")
def token_read(ctx):
    token = getattr(ctx, "token", None) or files.pod_token(str(ctx.directory / "token"))
    ctx.attempt(token)


# --- Health ------------------------------------------------------------------

@given("the site's database is down")
def database_down(monkeypatch):
    class Down(store.MemoryStore):
        def ping(self):
            raise OSError("connection refused")
    monkeypatch.setattr(main.Services, "store", Down())


@when("the store not made yet is checked")
def store_check(ctx):
    ctx.attempt(lambda: {"ok": (found := store.check(None)).ok, "plugin": found.plugin})


@given("an empty PostgreSQL database, from OPPORTUNITY_TEST_DATABASE_URL")
def postgres(ctx):
    url = os.environ.get("OPPORTUNITY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set OPPORTUNITY_TEST_DATABASE_URL to an empty database to test the PostgreSQL store")
    import psycopg
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS comments, reviews, schema_migrations")
    ctx.pg = store.PostgresStore(url)


@when("the store is migrated twice")
def migrated(ctx):
    ctx.attempt(lambda: [ctx.pg.migrate(), ctx.pg.migrate()])


@given("the store is migrated")
def migrated_once(ctx):
    ctx.pg.migrate()


@when("a thread with a reply and a review are kept, and both comments resolved by the controller")
def postgres_thread(ctx):
    me, controller = "reviewer@example.org", "owner@example.org"

    def thread():
        s = ctx.pg
        root = s.add_comment("OPP-10", "f:kill_point", "abc", me, "Why?")
        reply = s.add_comment("OPP-10", "", "abc", controller, "Because.", root.id)
        listed = [c.id for c in s.comments("OPP-10")] == [root.id, reply.id]
        s.add_review("OPP-10", "not-convinced", "", "abc", me)
        before = {k: list(v) for k, v in s.tally().items()}
        s.resolve(reply.id, controller)  # only a thread's first comment is resolved
        s.resolve(root.id, controller)
        return {"listed in order": listed, "reply's parent": s.comment(reply.id).parent_id == root.id,
                "tally before": before, "tally after": {k: list(v) for k, v in s.tally().items()},
                "root resolved by": s.comment(root.id).resolved_by, "reply resolved by": s.comment(reply.id).resolved_by,
                "review": s.reviews("OPP-10")[0].label}
    ctx.attempt(thread)


@when(parsers.parse('a review "{verdict}" is kept'))
def postgres_bad_review(ctx, verdict):
    ctx.attempt(lambda: ctx.pg.add_review("OPP-10", verdict, "", "abc", "reviewer@example.org"))


# --- Checks pubtest has no step for (candidates) ------------------------------

@then(parsers.re(r'the refusal\'s "(?P<key>[^"]+)" is "(?P<wanted>.*)"'))
def refusal_key(ctx, key, wanted):
    """The refusal's attribute at the dotted key; `__class__.__name__` is its class."""
    from pubtest.core import dig, same
    ctx.refusal_read = True
    assert ctx.refused is not None, f"it was not refused: the result is {show(ctx.result)}"
    got = dig(ctx.refused.error, key)
    assert same(got, wanted), f"the refusal's {key} is {show(got)}, not {wanted}"


@then(parsers.parse('the answer includes "{first}" before "{second}"'))
def answer_order(ctx, first, second):
    text = ctx.answer.text
    assert first in text and second in text, f"the answer has no {first!r} or no {second!r}"
    assert text.index(first) < text.index(second), f"{second!r} comes before {first!r}"
