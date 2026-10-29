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
like auth (Sustenaut/auth):

| Piece | Where |
|---|---|
| The app | `k8s/app.yaml`: one replica, private image `ghcr.io/schryer/sustenaut-opportunity`, the checkout in an emptyDir. No ingress points at it, and `k8s/admin/network-policy.yaml` lets only oauth2-proxy reach it. |
| PostgreSQL 16 | `k8s/postgres.yaml`, on the server's data volume; only the app and the backup job may reach it. |
| oauth2-proxy | `k8s/oauth2-proxy.yaml`: sign-in with the team realm at auth.sustenaut.eu (`keycloak-oidc`, issuer `https://auth.sustenaut.eu/realms/team`, PKCE S256: a passkey or an emailed code; accounts only for `var.team`, `Sustenaut/auth's invite-team.sh`), and as a second check only the emails in `var.team` (from `terraform output opportunity`, the list review and plan use). It passes the account's verified email on in `X-Forwarded-Email`, the only identity header the app trusts. `/healthz` and `/storage-in-use.json` are open without sign-in. |
| Sign-in client | sustenaut.eu's client in the team realm, registered by sustenaut.eu itself and approved by a DNS record (`register-client.sh`, Sustenaut/auth's `README.md`). It is kept on the server and in the Secret `opportunity-oidc`, nowhere else. |
| Ingress | `k8s/ingress.yaml`: opportunity.sustenaut.eu to oauth2-proxy, through Traefik with Let's Encrypt. The DNS record is the `opportunity` site in `pubkit.json`. |
| Backups | `k8s/backup.yaml`: a nightly `pg_dump` to the bucket `sustenaut-opportunity-backups` (`infra/opportunity.tf`, kept 30 days). |
| Secrets | `push-secrets.sh` puts in the Secret `opportunity-secrets`, the image pull secret `ghcr-pull` and the network policy, over the admin key; `register-client.sh` the Secret `opportunity-oidc`. |
| Deploys | `.github/workflows/opportunity-site.yml` builds and pushes the image, then sends the rendered `k8s/` over SSH to `sustenaut-deploy opportunity`, like Sustenaut/auth's `auth.yml`. |

When `var.team` changes: `terraform apply`, then `SUSTENAUT_SERVER=sustenaut ./with-secrets ./invite-team.sh` in a Sustenaut/auth checkout
(accounts in the team realm: invitations for new people, disabled for removed ones),
then `push-secrets.sh` again and restart both deployments (its header says how).

### Going live

What only David does, in this order. Nothing here has been applied, pushed,
registered, invited or deployed yet. Steps 1 to 7 of Sustenaut/auth's `README.md`,
"Deploying", are done first (the server, the tailnet, the deploy secrets).

1. **GitHub App** on schryer/business-plan: Repository permissions *Contents: Read
   and write* and *Pull requests: Read and write*, no webhook. Install it on
   business-plan only and generate a private key. Note the App ID and the
   installation ID (from the installation's URL).
2. **A ghcr pull token**: a classic personal access token with only `read:packages`.
3. **Bitwarden** (project Sustenaut): `opportunity-db-password` (random),
   `opportunity-cookie-secret` (`openssl rand -base64 32 | tr -- '+/' '-_'`),
   `opportunity-github-app-id`, `opportunity-github-app-key` (the PEM),
   `opportunity-github-installation-id`, `opportunity-ghcr-pull-token`. No sign-in
   client secret: step 7 registers it. For the team realm's email: the alias
   `noreply@sustenaut.eu` on the mailbox.org account whose app password is already
   `auth-smtp-password`.
4. `./with-secrets terraform -chdir=infra apply`: the backup bucket, its account and
   key, the DNS record for opportunity.sustenaut.eu, and the `auth_team` output.
5. **The team realm**: run the `auth` workflow (or merge), so the realm job creates
   the realm; then `SUSTENAUT_SERVER=sustenaut ./with-secrets ./invite-team.sh` in a Sustenaut/auth checkout. Everyone in
   `var.team` and the registrant (`var.team_registrant`, default `admin@sustenaut.eu`)
   get an invitation; set up the registrant's passkey from it (or use a code later).
6. Make the namespace on the running server, once: `ssh root@sustenaut sustenaut-app
   opportunity`; then `./with-secrets opportunity-site/push-secrets.sh`.
7. **Register the sign-in client**: `opportunity-site/register-client.sh`. Sign in at
   the link it prints as the registrant and confirm. It writes the approval record into
   `infra/auth-approvals.json`: commit that (a PR), merge,
   `./with-secrets terraform -chdir=infra apply`, and run `register-client.sh` again
   (sign in again). Once auth.sustenaut.eu sees the record (DNSSEC-validated, so the
   sustenaut.eu DNSSEC move must be live), the client is issued and put in the Secret
   `opportunity-oidc`.
8. **First deploy**: merge (or run the **opportunity site** workflow by hand). Then
   open https://opportunity.sustenaut.eu and sign in with your passkey or a code. A
   deploy before step 7 leaves oauth2-proxy waiting for the Secret `opportunity-oidc`
   (its pod doesn't start, the workflow's wait times out); run the workflow again after
   step 7.
9. After the first push, check that the ghcr package `sustenaut-opportunity` is
   **private**.

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
make opportunity   # http://localhost:8002: this checkout's cards, fake threads, proposals in build/
```

`tests/test_opportunity_site.py` runs on a temporary git checkout of the
cards with a fake GitHub. Set `OPPORTUNITY_TEST_DATABASE_URL` to an empty
PostgreSQL database to test the PostgreSQL store too, for example:

```sh
podman run -d --rm --name opp-pg -e POSTGRES_PASSWORD=test -p 55432:5432 docker.io/library/postgres:17
OPPORTUNITY_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres .venv/bin/python -m pytest tests/test_opportunity_site.py
```
