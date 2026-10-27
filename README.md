# opportunity-site

The opportunity cards (`opportunities/OPP-nn.md`) and the research reports
under them (`opportunities/research/`), for the team to read, comment on,
review and propose changes to, at opportunity.sustenaut.eu. Steps 2 (the app) and 4 (hosting, below) of the opportunity site (design
approved 2026-10-27).

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

**Files.** Attachments and client documents (uploaded `kept`, so never cleaned up) will live in
storage.sustenaut.eu (tenant `opportunity`), not git. `opportunity/files.py`
has the interface, a client for storage's `POST /opportunity/files` (with
the GitHub App's installation token, naming the person in `for`) and a
fake. The upload button stays disabled until the site records its uploads
and publishes `/storage-in-use.json`, and storage is deployed.

Pages are server-rendered forms. The only script picks a comment's anchor
without a reload; without it, the same links reload the page with the
anchor chosen. A form post must come from the site's own pages (its
`Origin` is checked).

## Settings

| Variable | What |
|---|---|
| `OPPORTUNITY_LOGIN` | `proxy` (default): trust the email oauth2-proxy sets in `X-Forwarded-Email` (it replaces whatever the browser sent; `OPPORTUNITY_EMAIL_HEADER` names another header). The site must only be reachable through the proxy. `wallet` (OIDC client `opportunity` at auth.sustenaut.eu, like review-site) is not built yet and fails closed. |
| `TEAM` | Comma-separated emails allowed in: the same Terraform `var.team` that review and plan get. |
| `OPPORTUNITY_OWNER` | David's email: may resolve any thread. |
| `OPPORTUNITY_DATABASE_URL` | PostgreSQL. `opportunity/migrations/*.sql` are applied in name order at start. |
| `OPPORTUNITY_REPO_DIR`, `OPPORTUNITY_REPO_URL` | The checkout of business-plan main, cloned if missing. `OPPORTUNITY_PULL=0` stops pulling. |
| `OPPORTUNITY_GITHUB_APP_ID`, `OPPORTUNITY_GITHUB_APP_KEY`, `OPPORTUNITY_GITHUB_INSTALLATION_ID` | The GitHub App (contents and pull requests: write, on schryer/business-plan) that opens pull requests. Its installation token also lets git pull the private repository. |
| `OPPORTUNITY_DEV_USER` | Local only, stands in for the login; refused on a cluster. |

Without a database URL or GitHub App, the site keeps comments in memory and
writes proposals under `OPPORTUNITY_PROPOSALS_DIR`; both are refused on a
cluster.

## Hosting

On the Sustenaut k3s server (`infra/hetzner.tf`), namespace `opportunity`,
like auth (`services/auth/`):

| Piece | Where |
|---|---|
| The app | `k8s/app.yaml`: one replica, private image `ghcr.io/schryer/sustenaut-opportunity`, the checkout in an emptyDir. No ingress points at it, and `k8s/admin/network-policy.yaml` lets only oauth2-proxy reach it. |
| PostgreSQL 16 | `k8s/postgres.yaml`, on the server's data volume; only the app and the backup job may reach it. |
| oauth2-proxy | `k8s/oauth2-proxy.yaml`: Google sign-in, only the emails in `var.team` (from `terraform output opportunity`, the list review and plan use). It passes the account on in `X-Forwarded-Email`. `/healthz` and `/storage-in-use.json` are open without sign-in. |
| Ingress | `k8s/ingress.yaml`: opportunity.sustenaut.eu to oauth2-proxy, through Traefik with Let's Encrypt. The DNS record is the `opportunity` site in `pubkit.json`. |
| Backups | `k8s/backup.yaml`: a nightly `pg_dump` to the bucket `sustenaut-opportunity-backups` (`infra/opportunity.tf`, kept 30 days). |
| Secrets | `push-secrets.sh` puts in the Secret `opportunity-secrets`, the image pull secret `ghcr-pull` and the network policy, over the admin key. |
| Deploys | `.github/workflows/opportunity-site.yml` builds and pushes the image, then sends the rendered `k8s/` over SSH to `sustenaut-deploy opportunity`, like `auth.yml`. |

When `var.team` changes, run `push-secrets.sh` again and restart both
deployments (its header says how).

Restore a dump (as for auth):

```sh
gcloud storage cp gs://sustenaut-opportunity-backups/opportunity-<when>.dump .
ssh root@sustenaut k3s kubectl -n opportunity exec -i postgres-0 -- \
  pg_restore -U opportunity -d opportunity --clean --if-exists < opportunity-<when>.dump
```

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
