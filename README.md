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
| oauth2-proxy | `k8s/oauth2-proxy.yaml`: sign-in with the team realm at auth.sustenaut.eu (`keycloak-oidc`, issuer `https://auth.sustenaut.eu/realms/team`, PKCE S256: a passkey or an emailed code), letting in only people with the role `opportunity` (`--oidc-groups-claim=access --allowed-group=opportunity`, from the `access` claim Sustenaut/auth's team realm puts in the token), and refreshing every 4 minutes (`--cookie-refresh=4m`), which also keeps the access token valid. It passes the account's verified email on in `X-Forwarded-Email` and that token in `X-Forwarded-Access-Token`, the only identity headers the app trusts. `/healthz` is open without sign-in, as is `/storage-in-use.json` until `k8s/oauth2-proxy.yaml` drops its route: nothing serves or needs it now. |
| Sign-in client | sustenaut.eu's client in the team realm, registered by sustenaut.eu itself and approved by a DNS record (`register-client.sh`, Sustenaut/auth's `README.md`). It is kept on the server and in the Secret `opportunity-oidc`, nowhere else. |
| Ingress | `k8s/ingress.yaml`: opportunity.sustenaut.eu to oauth2-proxy, through Traefik with Let's Encrypt. The DNS record is the `opportunity` site in shared-infra's `pubkit.json`. |
| Backups | `k8s/backup.yaml`: a nightly `pg_dump` to the bucket `sustenaut-opportunity-backups` (`infra/main.tf`, kept 30 days). |
| Secrets | `push-secrets.sh` puts in the Secret `opportunity-secrets` and the network policy, over the admin key; `register-client.sh` the Secret `opportunity-oidc`. |
| Deploys | `.github/workflows/deploy.yml` builds and pushes the image, then sends the rendered `k8s/` over SSH to `sustenaut-deploy opportunity`, like Sustenaut/auth's `auth.yml`. |

**Who may use the site** is the role `opportunity` on the team access page, https://auth.sustenaut.eu/realms/team/access (Sustenaut/auth's `README.md`): invite, tick, remove. No Terraform, no secrets pushed, no restarts. A `controller` has every role and may resolve any thread. `register-client.sh` declares the role.

**A change reaches the site at the person's next request.** On each request the app compares the realm's hash of who holds what with the one stored for that person, and only if it differs asks userinfo (`opportunity/access_check.py`, a copy of Sustenaut/auth's; its `README.md`, "Checking access on each request"). Nothing runs between requests, so a site nobody is using asks nothing. If auth.sustenaut.eu can't be reached, people go on reading and changes are refused.

This needs Sustenaut/auth's access-state endpoint deployed, with its key (`push-secrets.sh` there). When this version first deploys, deploy first and run `push-secrets.sh` after it, which takes `team`, `team-emails` and `owner` out of the Secret: a pod of the version before needs them to start. Everyone on the site must hold `opportunity` before then (Sustenaut/auth's `import-team-access.sh`).

### Going live

How the site went live, in order; the same steps stand up a new server. Terraform runs in a
shared-infra checkout beside this one (`SHARED_INFRA` names another path), with its `./with-secrets`. Steps 1 to 7 of Sustenaut/auth's `README.md`,
"Deploying", are done first (the server, the tailnet, the deploy secrets).

1. **GitHub App** (owned by the Sustenaut org) on Sustenaut/business-plan: Repository permissions *Contents: Read
   and write* and *Pull requests: Read and write*, no webhook. Install it on
   business-plan only and generate a private key. Note the App ID and the
   installation ID (from the installation's URL).
2. **Bitwarden** (project Sustenaut): `opportunity-db-password` (random),
   `opportunity-cookie-secret` (`openssl rand -base64 32 | tr -- '+/' '-_'`),
   `opportunity-github-app-id`, `opportunity-github-app-key` (the PEM),
   `opportunity-github-installation-id`. No sign-in
   client secret: step 6 registers it. For the team realm's email: the alias
   `noreply@sustenaut.eu` on the mailbox.org account whose app password is already
   `auth-smtp-password`.
3. `./with-secrets terraform -chdir=infra apply` here: the backup bucket and its account.
   In shared-infra, the same: the DNS record for opportunity.sustenaut.eu, and the
   `auth_team` output. Then the account's key, with your Bitwarden write token:
   `./pubkit service-account-key create --account=sustenaut-opportunity-backup@sustenaut.iam.gserviceaccount.com --secret=opportunity-backup-gcs-key`.
4. **The team realm**: run the `auth` workflow (or merge), so the realm job creates
   the realm; then `SUSTENAUT_SERVER=sustenaut ./with-secrets ./invite-team.sh` in a Sustenaut/auth checkout. Everyone in
   `var.team` and the registrant (`var.team_registrant`, default `admin@sustenaut.eu`)
   get an invitation; set up the registrant's passkey from it (or use a code later).
   Then, once, `SUSTENAUT_SERVER=sustenaut ./with-secrets ./import-team-access.sh` there: everyone
   in `var.team` gets the role `opportunity` (and the other services'), David `controller`.
5. Make the namespace on the running server, once: `ssh root@sustenaut sustenaut-app
   opportunity`; then `./with-secrets ./push-secrets.sh`.
6. **Register the sign-in client**: `./register-client.sh`. Sign in at
   the link it prints as the registrant and confirm. It writes the approval record into
   shared-infra's `infra/auth-approvals.json`: commit that (a PR there), merge,
   `./with-secrets terraform -chdir=infra apply`, and run `register-client.sh` again
   (sign in again). Once auth.sustenaut.eu sees the record (DNSSEC-validated, so the
   sustenaut.eu DNSSEC move must be live), the client is issued and put in the Secret
   `opportunity-oidc`.
7. **First deploy**: merge (or run the **deploy** workflow by hand). Then
   open https://opportunity.sustenaut.eu and sign in with your passkey or a code. A
   deploy before step 6 leaves oauth2-proxy waiting for the Secret `opportunity-oidc`
   (its pod doesn't start, the workflow's wait times out); run the workflow again after
   step 6.
8. The ghcr package `sustenaut-opportunity` is **public** and holds no private code, so the
   cluster pulls it without a secret. Give this repository write access under *Manage Actions access*.

If oauth2-proxy can't reach `https://auth.sustenaut.eu` from inside the cluster (it
fetches the issuer's discovery document at start, and exchanges codes there), its
log says so; the pod then stays unready.

Restore a dump (as for auth):

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
