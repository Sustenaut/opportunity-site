# opportunity-site

The opportunity cards (`opportunities/OPP-nn.md`) and the research reports
under them (`opportunities/research/`), for the team to read, comment on,
review and propose changes to, at opportunity.sustenaut.eu. The cards and this
site's GitHub App live in the private repository Sustenaut/business-plan; this
repository is the site.

The cards stay in git. The site reads a checkout of business-plan main,
pulled at most once a minute, and says on every page which commit it shows.
Edits become pull requests there; nothing changes until one is merged.

**The card format comes from that checkout too.** `bizplan.opportunities`
(its `FIELDS`, `read` and `rows`) reads the cards and works out the matrix
columns, beside the decision rules that stay private in business-plan. So
neither this repository nor its public image holds it: `opportunity/cardformat.py`
imports it from the checkout, afresh whenever the checkout moves, and needs only
what `requirements.txt` installs. A commit whose format fails to import is listed
as a problem, and the site reads on with the format it had.
business-plan's `tests/test_opportunity_contract.py` checks the real module still
gives what the site uses; this repository's tests run on a stand-in with the same
interface and made-up cards (`tests/fixtures/business-plan/`).

| Page | What it is |
|---|---|
| `/` | Every card, ranked by expected MVDS levels per 100 David hours, with kind, group, confidence, MVDS levels, open threads and reviews; filter by kind or group. The research reports. |
| `/c/<OPP-nn>` | A card: its fields, its body, the reports that name it, reviews, files and comment threads. |
| `/r/<slug>` | A research report, the same way. |
| `/c/<OPP-nn>/edit` | Propose an edit: each front-matter field (with the hints from the format's `FIELDS`) and the body. |
| `/r/new` | Add a research report. |

**Comments.** Pick a front-matter field or a section heading (the Comment
link beside it, or the form's "On" list) and comment; reply; resolve. The
author of a thread or a controller (the group `controller`) may resolve it. Each
comment keeps the commit it was made on.

**Reviews.** "Reviewed", "Reviewed with concerns" or "Not convinced", with
a short note, on the commit shown. A review made before the card or report
last changed is labelled "on an older version" (only a change to that file
counts, not any new commit on main).

**Edits.** The rule shown on the form: no dates or build details in
opportunity cards. Fields are edited as their YAML text, so the rest of
the file, comments included, stays as written. The edited card must read
cleanly with the format's `read` and give matrix rows; a report
must name cards that exist and list its sources. Then the site creates
branch `opportunity/<card or report>-<user>-<n>` and a pull request that
names the editor, in business-plan, through a GitHub App. If the file changed on main since
the form was loaded, nothing is opened and the form says to reload.

**Files.** Attachments and client documents will live in storage.sustenaut.eu (the
private tenant `opportunity`, which storage never cleans), not git. `opportunity/files.py`
has the interface, `StorageFiles` on integrations' storage client (the pod's token,
naming the person in `for` and the card in `subject`; a card's files are the tenant's
listing for that subject) and a fake. A card's or report's page has an upload form
(a file, an optional label, and "kept" for one that went to a client), and its files are
read back through the site (`/files/<id>/<name>`, always a download), as the tenant is
private. Both are there once the deployment sets `OPPORTUNITY_FILES_URL`; until then the
button stays disabled.

Pages are server-rendered forms. The only script picks a comment's anchor
without a reload; without it, the same links reload the page with the
anchor chosen. A form post must come from the site's own pages (its
`Origin` is checked).

## Settings

| Variable | What |
|---|---|
| `OPPORTUNITY_LOGIN` | `proxy` (default): trust the email and access token oauth2-proxy sets in `X-Forwarded-Email` and `X-Forwarded-Access-Token` (it replaces whatever the browser sent; `OPPORTUNITY_EMAIL_HEADER` names another header for the email), and need the role `opportunity`, asked on each request (`opportunity/access_check.py`). The site must only be reachable through the proxy. `wallet` (OIDC client `opportunity` at auth.sustenaut.eu, like review-site) is not built yet and fails closed. |
| `OPPORTUNITY_CLIENT_ID`, `OPPORTUNITY_CLIENT_SECRET` | The sign-in client, to read the access state's hash (the Secret `opportunity-oidc`); without them the proxy login fails closed. `OPPORTUNITY_AUTH_REALM` names another realm than `https://auth.sustenaut.eu/realms/team`. |
| `OPPORTUNITY_DEV_USER`, `OPPORTUNITY_DEV_GROUPS` | Locally only: stand in for the login and the roles (default `opportunity`); refused on a cluster. |
| `OPPORTUNITY_DATABASE_URL` | PostgreSQL. `opportunity/migrations/*.sql` are applied in name order at start. |
| `OPPORTUNITY_REPO_DIR`, `OPPORTUNITY_REPO_URL` | The checkout of business-plan main, cloned if missing. `OPPORTUNITY_PULL=0` stops pulling. |
| `OPPORTUNITY_GITHUB_APP_ID`, `OPPORTUNITY_GITHUB_APP_KEY`, `OPPORTUNITY_GITHUB_INSTALLATION_ID` | The GitHub App (contents and pull requests: write, on Sustenaut/business-plan) that opens pull requests. Its installation token also lets git pull the private repository. |
| `OPPORTUNITY_DEV_USER` | Local only, stands in for the login; refused on a cluster. |

Without a database URL or GitHub App, the site keeps comments in memory and
writes proposals under `OPPORTUNITY_PROPOSALS_DIR`; both are refused on a
cluster.

## Hosting

On the Sustenaut k3s server (shared-infra's `infra/hetzner.tf`), namespace `opportunity`,
like auth (Sustenaut/auth):

| Piece | Where |
|---|---|
| The app | `k8s/app.yaml`: one replica, image `ghcr.io/sustenaut/sustenaut-opportunity` (no cards, no bizplan), the checkout in an emptyDir. No ingress points at it, and `k8s/admin/network-policy.yaml` lets only oauth2-proxy reach it. |
| PostgreSQL 16 | `k8s/postgres.yaml`, on the server's data volume; only the app and the backup job may reach it. |
| oauth2-proxy | `k8s/oauth2-proxy.yaml`: sign-in with the team realm at auth.sustenaut.eu (`keycloak-oidc`, issuer `https://auth.sustenaut.eu/realms/team`, PKCE S256: a passkey or an emailed code), letting in only people with the role `opportunity` (`--oidc-groups-claim=access --allowed-group=opportunity`, from the `access` claim Sustenaut/auth's team realm puts in the token), and refreshing every 4 minutes (`--cookie-refresh=4m`), which also keeps the access token valid. It passes the account's verified email on in `X-Forwarded-Email` and that token in `X-Forwarded-Access-Token`, the only identity headers the app trusts. `/healthz` is open without sign-in. |
| Sign-in client | sustenaut.eu's client in the team realm, registered by sustenaut.eu itself and approved by a DNS record (the deploy walk's `auth.sign-in-client`, Sustenaut/auth's `README.md`). It is kept on the server and in the Secret `opportunity-oidc`, nowhere else. |
| Ingress | `k8s/ingress.yaml`: opportunity.sustenaut.eu to oauth2-proxy, through Traefik with Let's Encrypt. The DNS record is the `opportunity` site in shared-infra's `pubkit.json`. |
| Backups | Two layers, by [Sustenaut/pg-backup](https://github.com/Sustenaut/pg-backup): the write-ahead log archived by WAL-G within a minute, with a base backup each night, to `sustenaut-opportunity-wal` (`infra/main.tf`'s `module "wal"`, restorable to any moment in the last 14 days); and `k8s/backup.yaml`'s nightly `pg_dump` to `sustenaut-opportunity-backups` (kept 30 days). `backups/pg-backup.json` holds the site's settings, and `./backups/pg-backup` runs the pinned release. |
| Secrets | The deploy walk ("Deploying" below) puts in the Secrets `opportunity-secrets`, `opportunity-oidc` and `opportunity-wal` and the network policy, over the admin key. |
| Deploys | `.github/workflows/deploy.yml` builds and pushes the image, then sends the rendered `k8s/` over SSH to `sustenaut-deploy opportunity` once `DEPLOY_OPPORTUNITY` is `on`, like Sustenaut/auth's `auth.yml`. |

**Who may use the site** is the role `opportunity` on the team access page, https://auth.sustenaut.eu/realms/team/access (Sustenaut/auth's `README.md`): invite, tick, remove. No Terraform, no secrets pushed, no restarts. A `controller` has every role and may resolve any thread. The walk's `auth.sign-in-client` declares the role.

**A change reaches the site at the person's next request.** On each request the app compares the realm's hash of who holds what with the one stored for that person, and only if it differs asks userinfo (`opportunity/access_check.py`, a copy of Sustenaut/auth's; its `README.md`, "Checking access on each request"). Nothing runs between requests, so a site nobody is using asks nothing. If auth.sustenaut.eu can't be reached, people go on reading and changes are refused.

This needs Sustenaut/auth's access-state endpoint deployed, with its key (`push-secrets.sh` there).

## Deploying

`.github/workflows/deploy.yml` builds the image on each merge to main, once CI has
passed, and applies `k8s/` to namespace `opportunity` with pubkit's `k8s-deploy.yml`,
once `DEPLOY_OPPORTUNITY` is `on`.

pubkit.json's `deploy` block lists everything else the deployment needs, and pubkit's
deploy walk checks each need and makes what it can. `pg.database` is
[Sustenaut/pg-backup](https://github.com/Sustenaut/pg-backup)'s type: `deploy.providers`
pins its release, and `./pubkit` runs with it. To take the site live, or bring it back in
step, from a checkout of this repository with Sustenaut/shared-infra and Sustenaut/auth
checked out beside it, on a machine on the admin tailnet, signed in to `gh` and `gcloud`:

```sh
./with-secrets ./pubdeploy walk --fulfil --server sustenaut --zones ../shared-infra/pubkit.json
```

It checks every need, prints the plan, and waits for a typed `yes`; then it makes each
missing need it can, over the admin channel (`ssh root@sustenaut`), and checks it again.
Every run can run again: what is ready is left alone. In order:

| Need | What the walk does |
|---|---|
| the namespace `opportunity` | the server's `sustenaut-app`, which makes it and its deploy identity |
| `bitwarden.generated` `opportunity-cookie-secret` | oauth2-proxy's cookie secret: a new one of its shape, written to Bitwarden, when it is missing or misshapen |
| `gcp.service-account-key` `opportunity-backup-gcs-key` | the nightly dump's key for `sustenaut-opportunity-backup` (`infra/`'s account): made and written to Bitwarden when it is missing or not one of the account's live keys |
| the Secret `opportunity-secrets` | made from `opportunity-db-password`, the cookie secret, the GitHub App's three values and the backup key; the app and oauth2-proxy restarted |
| `auth.sign-in-client` | sustenaut.eu's team-site client in the team realm, role `opportunity`: the approval record written into shared-infra's `infra/auth-approvals.json` when auth.sustenaut.eu wants one, and once the client is issued, the Secret `opportunity-oidc` made from it on the server |
| `k8s.manifests` | `k8s/admin/network-policy.yaml` applied: only oauth2-proxy's pods may reach the app, and only the app and the dump the database |
| `pg.database` | the WAL archive's two keys in Bitwarden and the Secret `opportunity-wal`, as `./backups/pg-backup setup-secrets` makes them; then PostgreSQL, the archive and the last base backup checked |
| `DEPLOY_OPPORTUNITY` and the rollout | the gate on, once everything before it is ready, and `deploy.yml` run and waited for |
| `service.health` | `https://opportunity.sustenaut.eu/healthz` answers |

A new cookie secret, backup key or archive key wants a Bitwarden token that may write:
the walk asks for it once, at a hidden prompt, and keeps it only in its process. An
approval record is a change to shared-infra: commit it there, merge, apply, and run the
walk again.

Some needs it only checks, and says what a person does:

- **The values in Bitwarden** (project Sustenaut): `opportunity-db-password` (random,
  and kept: PostgreSQL holds it), and the GitHub App's `opportunity-github-app-id`,
  `opportunity-github-app-key` (the PEM) and `opportunity-github-installation-id`. The
  App is owned by the Sustenaut org and installed on Sustenaut/business-plan only, with
  *Contents* and *Pull requests: Read and write* and no webhook.
- **storage's tenants** in Sustenaut/storage's `tenants.json`: `opportunity` (the
  threads' files, which `k8s:opportunity/app` reads and writes) and
  `calls-opportunity-site` (the call log buffer the app writes). When one is missing,
  the fix is the entry to add there.
- **Its entries in other services' variables**: `opportunity-site` in integrations'
  `INGEST_DATASETS`, and `opportunity_site.app` in observability's
  `OBSERVABILITY_SENDERS`.
- **The DNS record** for `opportunity.sustenaut.eu`, in shared-infra's hosting block.
- **storage itself** (`upstream`).
- **The backup drill** (`pg.database`): `./backups/pg-backup drill --wait`, below, until
  pg-backup records the drill where the walk can read it.

`./pubdeploy walk` without `--fulfil` (or `pubdeploy check`) changes nothing, and
`./pubdeploy walk --offline` checks only the files. `.github/workflows/deploy-check.yml`
walks the deployment every 30 minutes, read-only, with the deploy key, and writes the walk
to storage's `plane` tenant; it fails when a need is missing, drift or blocked.

### A new server

Before the walk: steps 1 to 7 of Sustenaut/auth's `README.md`, "Deploying" (the server,
the tailnet, the deploy secrets); `./with-secrets terraform -chdir=infra apply` here (the
backup and WAL buckets and their accounts) and in shared-infra (the DNS record and the
`auth_team` output); and the team realm, with everyone in `var.team` holding the role
`opportunity` (Sustenaut/auth's `invite-team.sh` and `import-team-access.sh`). The ghcr
package `sustenaut-opportunity` is **public** and holds no private code, so the cluster
pulls it without a secret; give this repository write access under *Manage Actions access*.

If oauth2-proxy can't reach `https://auth.sustenaut.eu` from inside the cluster (it
fetches the issuer's discovery document at start, and exchanges codes there), its
log says so; the pod then stays unready.

**Backups:** run from the repository root, signed in to Sustenaut's tailnet:

| When | Command |
|---|---|
| Monthly, and after any change to the backups or PostgreSQL (right after a merge: `drill --wait`) | `./backups/pg-backup drill` |
| To look at the database as it was at a moment, in a scratch namespace | `./backups/pg-backup restore --to "2026-11-05 14:32:00+00"` |
| To put that restore back as the live database | `./backups/pg-backup promote opportunity-restore-<the namespace>` |
| Once, and after a rebuild: the archive's keys, into Bitwarden and the cluster | the deploy walk above (`pg.database`), or `./backups/pg-backup setup-secrets` |

pg-backup's README says what each does. Or restore a dump:

```sh
gcloud storage cp gs://sustenaut-opportunity-backups/opportunity-<when>.dump .
ssh root@sustenaut k3s kubectl -n opportunity exec -i postgres-0 -- \
  pg_restore -U opportunity -d opportunity --clean --if-exists < opportunity-<when>.dump
```

## Running it locally

```sh
uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements.lock
OPPORTUNITY_DEV_USER=$(git config user.email) OPPORTUNITY_DEV_GROUPS=opportunity,controller \
  OPPORTUNITY_REPO_DIR=../business-plan OPPORTUNITY_PULL=0 OPPORTUNITY_FIXTURES=fixtures/threads.json \
  .venv/bin/python -m uvicorn opportunity.main:app --reload --port 8002
```

That is http://localhost:8002: your business-plan checkout's cards, fake threads, proposals in `build/`.
Without access to business-plan, copy `tests/fixtures/business-plan` somewhere, `git init` and commit
it, and point `OPPORTUNITY_REPO_DIR` there.

`tests/test_opportunity_site.py` runs on a temporary git checkout of the fixture
cards and stand-in format with a fake GitHub. Set `OPPORTUNITY_TEST_DATABASE_URL` to an empty
PostgreSQL database to test the PostgreSQL store too, for example:

```sh
podman run -d --rm --name opp-pg -e POSTGRES_PASSWORD=test -p 55432:5432 docker.io/library/postgres:17
OPPORTUNITY_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres .venv/bin/python -m pytest tests/test_opportunity_site.py
```
