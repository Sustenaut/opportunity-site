"""The opportunity site: the cards and research reports, comments, reviews and
proposed edits.

    make opportunity       # run it locally on http://localhost:8002 with fake threads
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from opportunity import auth, content, edits, files, github, store

HERE = Path(__file__).resolve().parent
templates = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape())
templates.globals.update(quote=quote, verdicts=store.VERDICTS, note_chars=store.NOTE_CHARS, rule=edits.RULE)
templates.filters["short"] = lambda sha: (sha or "")[:7]
templates.filters["num"] = lambda v, d=1: "" if v is None else f"{v:.{d}f}".rstrip("0").rstrip(".")

app = FastAPI(title="Sustenaut opportunities", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


class Services:
    """Made once on first use; tests replace them."""

    content: content.Content | None = None
    store: store.Store | None = None
    publisher: github.Publisher | None = None
    files: files.Files | None = None
    _made = False

    @classmethod
    def get(cls) -> type[Services]:
        if not cls._made:
            cls._made = True
            cluster = auth.on_cluster()
            if cls.publisher is None:
                cls.publisher = github.from_env(cluster)
            if cls.content is None:
                app_token = getattr(cls.publisher, "token", None)  # the GitHub App can also read the repo
                cls.content = content.from_env(app_token)
            if cls.store is None:
                cls.store = store.from_env(cluster)
            if cls.files is None:
                cls.files = files.from_env()
        return cls


def page(name: str, status_code: int = 200, **values) -> HTMLResponse:
    return HTMLResponse(templates.get_template(name).render(**values), status_code=status_code)


async def _form(request: Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}


@app.get("/healthz")
def healthz():
    return {"ok": True}


# --- Reading -----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(kind: str = "", group: str = "", who: auth.Person = Depends(auth.person)):
    s = Services.get()
    snap = s.content.now()
    rows = snap.rows()
    shown = [r for r in rows if (not kind or r["kind"] == kind) and (not group or r["group"] == group)]
    shown.sort(key=lambda r: (r["expected levels per 100 h"] is None, -(r["expected levels per 100 h"] or 0)))
    return page("index.html", who=who, snap=snap, rows=shown, kind=kind, group=group, tally=s.store.tally(),
                kinds=sorted({r["kind"] for r in rows if r["kind"]}),
                groups=sorted({r["group"] for r in rows if r["group"]}))


_HEADING = re.compile(r'<h([1-6]) id="([^"]+)">(.*?)</h\1>', re.S)


def _with_comment_links(body_html: str, here: str) -> Markup:
    """Each section heading gets a Comment link that picks it as the anchor (no script needed)."""
    def link(m):
        return (f'<h{m[1]} id="{m[2]}">{m[3]} <a class="pick" data-anchor="s:{m[2]}" '
                f'href="{here}?anchor=s:{m[2]}#comment">Comment</a></h{m[1]}>')
    return Markup(_HEADING.sub(link, body_html))


def _threads(s, subject: str, path: str) -> list[dict]:
    """Comment threads, open first, each with its replies and whether it was on an older version."""
    every = s.store.comments(subject)
    roots = [c for c in every if c.parent_id is None]
    out = [{"root": r, "replies": [c for c in every if c.parent_id == r.id],
            "older": not s.content.current(path, r.commit_sha)} for r in roots]
    return sorted(out, key=lambda t: bool(t["root"].resolved_by))


def _subject_page(who, item: dict, subject: str, here: str, *, kind: str, status_code=200, **extra):
    s = Services.get()
    snap = s.content.now()
    body_html, sections = content.render(item["body"])
    skip = {"file", "body", "warning", "path", "text"}
    fields = [(k, v) for k, v in item.items() if k not in skip]
    anchors = ([("", f"All of this {kind}")] + [(f"f:{k}", f"Field: {k}") for k, _ in fields]
               + [(a, f"Section: {t}") for a, t in sections])
    reviews = [{"r": r, "older": not s.content.current(item["path"], r.commit_sha)}
               for r in s.store.reviews(subject)]
    return page(f"{kind}.html", status_code=status_code, who=who, snap=snap, item=item, subject=subject,
                here=here, fields=fields, body=_with_comment_links(body_html, here), anchors=dict(anchors),
                threads=_threads(s, subject, item["path"]), reviews=reviews, uploads=s.files,
                attached=s.files.list(subject) if s.files else [], **extra)


def _card(card_id: str) -> dict:
    found = Services.get().content.now().cards.get(card_id)
    if not found:
        raise HTTPException(404, "No such card")
    return found


def _report(slug: str) -> dict:
    found = Services.get().content.now().reports.get(slug)
    if not found:
        raise HTTPException(404, "No such report")
    return found


@app.get("/c/{card_id}", response_class=HTMLResponse)
def card(card_id: str, anchor: str = "", who: auth.Person = Depends(auth.person)):
    item = _card(card_id)
    return _subject_page(who, item, card_id, f"/c/{quote(card_id)}", kind="card", anchor=anchor,
                         reports=Services.get().content.now().reports_for(card_id))


@app.get("/r/new", response_class=HTMLResponse)
def report_form(card: str = "", who: auth.Person = Depends(auth.person)):
    snap = Services.get().content.now()
    return page("report_new.html", who=who, snap=snap, form={"cards": card})


@app.get("/r/{slug}", response_class=HTMLResponse)
def report(slug: str, anchor: str = "", who: auth.Person = Depends(auth.person)):
    item = _report(slug)
    return _subject_page(who, item, f"research/{slug}", f"/r/{quote(slug)}", kind="report", anchor=anchor,
                         slug=slug)


# --- Comments and reviews ----------------------------------------------------

def _resolve_subject(subject: str) -> tuple[dict, str, str]:
    """(item, page path, kind) for a card id or research/<slug>."""
    if subject.startswith("research/"):
        slug = subject.removeprefix("research/")
        return _report(slug), f"/r/{quote(slug)}", "report"
    return _card(subject), f"/c/{quote(subject)}", "card"


async def _comment(subject: str, request: Request, who: auth.Person):
    s = Services.get()
    item, here, kind = _resolve_subject(subject)
    f = await _form(request)
    text = f.get("body", "").strip()
    parent = None
    if f.get("parent"):
        root = s.store.comment(int(f["parent"])) if f["parent"].isdigit() else None
        if not root or root.card_or_report != subject or root.parent_id is not None:
            raise HTTPException(404, "No such thread")
        parent = root.id
    if not text:
        extra = {"reports": s.content.now().reports_for(subject)} if kind == "card" else {"slug": here[3:]}
        return _subject_page(who, item, subject, here, kind=kind, status_code=422, anchor=f.get("anchor", ""),
                             error="Write something before posting.", **extra)
    sha = f.get("sha") or s.content.now().sha
    anchor = "" if parent else f.get("anchor", "")
    made = s.store.add_comment(subject, anchor, sha, who.email, text, parent)
    return RedirectResponse(f"{here}#c{parent or made.id}", status_code=303)


async def _review(subject: str, request: Request, who: auth.Person):
    s = Services.get()
    item, here, kind = _resolve_subject(subject)
    f = await _form(request)
    verdict, note = f.get("verdict", ""), f.get("note", "").strip()
    if verdict not in store.VERDICTS or len(note) > store.NOTE_CHARS:
        extra = {"reports": s.content.now().reports_for(subject)} if kind == "card" else {"slug": here[3:]}
        return _subject_page(who, item, subject, here, kind=kind, status_code=422,
                             error=f"Pick a verdict, and keep the note under {store.NOTE_CHARS} characters.",
                             **extra)
    s.store.add_review(subject, verdict, note, f.get("sha") or s.content.now().sha, who.email)
    return RedirectResponse(f"{here}#reviews", status_code=303)


@app.post("/c/{card_id}/comments", dependencies=[Depends(auth.same_origin)])
async def comment_card(card_id: str, request: Request, who: auth.Person = Depends(auth.person)):
    return await _comment(card_id, request, who)


@app.post("/r/{slug}/comments", dependencies=[Depends(auth.same_origin)])
async def comment_report(slug: str, request: Request, who: auth.Person = Depends(auth.person)):
    return await _comment(f"research/{slug}", request, who)


@app.post("/c/{card_id}/reviews", dependencies=[Depends(auth.same_origin)])
async def review_card(card_id: str, request: Request, who: auth.Person = Depends(auth.person)):
    return await _review(card_id, request, who)


@app.post("/r/{slug}/reviews", dependencies=[Depends(auth.same_origin)])
async def review_report(slug: str, request: Request, who: auth.Person = Depends(auth.person)):
    return await _review(f"research/{slug}", request, who)


@app.post("/comments/{cid}/resolve", dependencies=[Depends(auth.same_origin)])
def resolve(cid: int, who: auth.Person = Depends(auth.person)):
    s = Services.get()
    root = s.store.comment(cid)
    if not root or root.parent_id is not None:
        raise HTTPException(404, "No such thread")
    if not who.may_resolve(root.author_email):
        raise HTTPException(403, "Only the thread's author or the owner can resolve it")
    _, here, _ = _resolve_subject(root.card_or_report)
    s.store.resolve(cid, who.email)
    return RedirectResponse(f"{here}#c{cid}", status_code=303)


# --- Proposing changes -------------------------------------------------------

def _edit_page(who, item, card_id, *, status_code=200, error="", values=None, body=None, note="", sha=None):
    snap = Services.get().content.now()
    fields = edits.fields_for(item["text"])
    if values:
        fields = [(k, values.get(k, v)) for k, v in fields]
    _, old_body = edits.split(item["text"])
    return page("card_edit.html", status_code=status_code, who=who, snap=snap, item=item, card_id=card_id,
                fields=fields, hints=edits.hints(), body=old_body if body is None else body, note=note,
                error=error, sha=sha or snap.sha)


@app.get("/c/{card_id}/edit", response_class=HTMLResponse)
def edit_form(card_id: str, who: auth.Person = Depends(auth.person)):
    return _edit_page(who, _card(card_id), card_id)


def _pr_body(who: auth.Person, sha: str, note: str, what: str) -> str:
    lines = [f"{what}, proposed by **{who.email}** on the opportunity site "
             f"(https://opportunity.sustenaut.eu), starting from {sha[:7]}."]
    if note.strip():
        lines += ["", note.strip()]
    lines += ["", "Merging this changes the card for everyone; until then the site shows main as it is."]
    return "\n".join(lines)


@app.post("/c/{card_id}/edit", dependencies=[Depends(auth.same_origin)])
async def edit(card_id: str, request: Request, who: auth.Person = Depends(auth.person)):
    s = Services.get()
    item = _card(card_id)
    f = await _form(request)
    values = {k[2:]: v for k, v in f.items() if k.startswith("f:")}
    body, note, sha = f.get("body", ""), f.get("note", ""), f.get("sha", "")
    try:
        new = edits.edit_card(item["text"], values, body)
        edits.check_card(item["file"], item["text"], new)
        url = s.publisher.propose(
            slug=card_id, user=who.handle, changes=[github.Change(item["path"], item["text"], new)],
            title=f"{card_id}: edit from the opportunity site",
            body=_pr_body(who, sha or s.content.now().sha, note, f"An edit to {card_id} {item.get('name', '')}"))
    except (edits.Invalid, github.Conflict) as e:
        return _edit_page(who, item, card_id, status_code=422, error=str(e), values=values, body=body,
                          note=note, sha=sha)
    return page("proposed.html", who=who, snap=s.content.now(), url=url, back=f"/c/{quote(card_id)}",
                what=f"your edit to {card_id}")


@app.post("/r/new", dependencies=[Depends(auth.same_origin)])
async def add_report(request: Request, who: auth.Person = Depends(auth.person)):
    s = Services.get()
    snap = s.content.now()
    f = await _form(request)
    try:
        path, text = edits.new_report(f.get("slug", ""), f.get("title", ""), f.get("cards", ""),
                                      f.get("summary", ""), f.get("sources", ""), f.get("body", ""),
                                      known=set(snap.cards), taken=set(snap.reports))
        slug = Path(path).stem
        url = s.publisher.propose(slug=slug, user=who.handle, changes=[github.Change(path, None, text)],
                                  title=f"Research report: {f['title'].strip()}",
                                  body=_pr_body(who, snap.sha, f.get("note", ""), f"A research report, {path}"))
    except (edits.Invalid, github.Conflict) as e:
        return page("report_new.html", status_code=422, who=who, snap=snap, form=f, error=str(e))
    return page("proposed.html", who=who, snap=snap, url=url, back="/", what="the new report")
