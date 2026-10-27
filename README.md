# opportunity-site

The opportunity cards (`opportunities/OPP-nn.md`) and the research reports
under them (`opportunities/research/`), for the team to read, comment on,
review and propose changes to, at opportunity.sustenaut.eu. This is step 2
of the opportunity site (design approved 2026-10-27): the app. Hosting, DNS
and the deploy workflow are step 4.

The cards stay in git. The site reads a checkout of business-plan main,
pulled at most once a minute, and says on every page which commit it shows.
Edits become pull requests; nothing changes until one is merged.

| Page | What it is |
|---|---|
| `/` | Every card, ranked by expected MVDS levels per 100 David hours, with kind, group, confidence, MVDS levels, open threads and reviews; filter by kind or group. The research reports. |
| `/c/<OPP-nn>` | A card: its fields, its body, the reports that name it, reviews, files and comment threads. |
| `/r/<slug>` | A research report, the same way. |
| `/c/<OPP-nn>/edit` | Propose an edit: each front-matter field (with the hints from `bizplan.opportunities.FIELDS`) and the body. |
| `/r/new` | Add a research report. |

**Comments.** Pick a front-matter field or a section heading (the Comment
link beside it, or the form's "On" list) and comment; reply; resolve. The
author of a thread or the owner (`OPPORTUNITY_OWNER`) may resolve it. Each
comment keeps the commit it was made on.

**Reviews.** "Reviewed", "Reviewed with concerns" or "Not convinced", with
a short note, on the commit shown. A review made before the card or report
last changed is labelled "on an older version" (only a change to that file
counts, not any new commit on main).

**Edits.** The rule shown on the form: no dates or build details in
opportunity cards. Fields are edited as their YAML text, so the rest of
the file, comments included, stays as written. The edited card must read
cleanly with `bizplan.opportunities.read` and give matrix rows; a report
must name cards that exist and list its sources. Then the site creates
branch `opportunity/<card or report>-<user>-<n>` and a pull request that
names the editor, through a GitHub App. If the file changed on main since
the form was loaded, nothing is opened and the form says to reload.

**Files.** Attachments and versioned client documents will live in
storage.sustenaut.eu (tenant `opportunity`), not git. `opportunity/files.py`
has the interface and a fake; the upload button is disabled until the
storage service takes general files server-side (its own PR first).

Pages are server-rendered forms. The only script picks a comment's anchor
without a reload; without it, the same links reload the page with the
anchor chosen. A form post must come from the site's own pages (its
`Origin` is checked).

## Settings

| Variable | What |
|---|---|
| `OPPORTUNITY_LOGIN` | `proxy` (default): trust the email oauth2-proxy sets in `X-Auth-Request-Email` or `X-Forwarded-Email`. The site must only be reachable through the proxy. `wallet` (OIDC client `opportunity` at auth.sustenaut.eu, like review-site) is not built yet and fails closed. |
| `TEAM` | Comma-separated emails allowed in: the same Terraform `var.team` that review and plan get. |
| `OPPORTUNITY_OWNER` | David's email: may resolve any thread. |
| `OPPORTUNITY_DATABASE_URL` | PostgreSQL. `opportunity/migrations/*.sql` are applied in name order at start. |
| `OPPORTUNITY_REPO_DIR`, `OPPORTUNITY_REPO_URL` | The checkout of business-plan main, cloned if missing. `OPPORTUNITY_PULL=0` stops pulling. |
| `OPPORTUNITY_GITHUB_APP_ID`, `OPPORTUNITY_GITHUB_APP_KEY`, `OPPORTUNITY_GITHUB_INSTALLATION_ID` | The GitHub App (contents and pull requests: write, on schryer/business-plan) that opens pull requests. Its installation token also lets git pull the private repository. |
| `OPPORTUNITY_DEV_USER` | Local only, stands in for the login; refused on a cluster. |

Without a database URL or GitHub App, the site keeps comments in memory and
writes proposals under `OPPORTUNITY_PROPOSALS_DIR`; both are refused on a
cluster.

## Running it locally

```sh
make opportunity   # http://localhost:8002: this checkout's cards, fake threads, proposals in build/
```

`tests/test_opportunity_site.py` runs on a temporary git checkout of the
cards with a fake GitHub. Set `OPPORTUNITY_TEST_DATABASE_URL` to an empty
PostgreSQL database to test the PostgreSQL store too, for example:

```sh
podman run -d --rm --name opp-pg -e POSTGRES_PASSWORD=test -p 55432:5432 docker.io/library/postgres:17
OPPORTUNITY_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres .venv/bin/python -m pytest tests/test_opportunity_site.py
```
