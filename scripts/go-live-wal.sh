#!/usr/bin/env bash
# Makes the site's WAL archive ready for PostgreSQL to archive into: the bucket and its account
# (infra/'s module "wal", from #23), WAL-G's two keys in Bitwarden, and the Secret
# opportunity-wal in the cluster. Run it once, after #23 has merged and before #24 (the pod
# change, which this script ships with) does: the new pod needs the Secret to start. It doesn't
# need #24 merged. Run it from #24's branch, which holds main: it stops unless infra/ and
# backups/ here are exactly origin/main's, so the apply is what main holds. Signed in to gcloud
# and to Sustenaut's tailnet:
#
#   git fetch origin && git switch --detach origin/claude/wal-archiving && scripts/go-live-wal.sh
#
# Afterwards `git latest` takes the checkout back to main.
#
# Each step says what it does and asks first; a step already done is skipped, and the first
# error stops it. setup-secrets asks for a Bitwarden access token with write access to the
# Sustenaut project at a hidden prompt. It prints no secret.
set -euo pipefail
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
server=${SUSTENAUT_SERVER:-sustenaut}

step() { printf '\n== %s\n' "$*"; }
skip() { echo "   already done: $*"; }
ask() {
  local answer
  read -r -p "   $1 [y/N] " answer </dev/tty
  [[ $answer =~ ^[Yy] ]] || { echo "Stopped; run scripts/go-live-wal.sh again to go on."; exit 1; }
}
on_server() { ssh -o BatchMode=yes "root@$server" "$@"; }

cd "$root"
step "0. infra/ and backups/ are main's, with #23"
git fetch -q origin main
if ! git cat-file -e origin/main:backups/pg-backup.json 2>/dev/null; then
  echo "   origin/main doesn't have #23 yet: merge it first" >&2
  exit 1
fi
if ! git diff --quiet origin/main -- infra backups; then
  echo "   infra/ or backups/ here differ from origin/main: git fetch origin && git switch --detach origin/claude/wal-archiving" >&2
  exit 1
fi
echo "   yes, at origin/main $(git rev-parse --short origin/main)"

step "1. The bucket sustenaut-opportunity-wal, its account and the chunk-delete role"
if gcloud storage buckets describe gs://sustenaut-opportunity-wal >/dev/null 2>&1; then
  skip "the bucket is there"
else
  ./with-secrets terraform -chdir=infra init -input=false >/dev/null
  ./with-secrets terraform -chdir=infra plan -input=false
  ask "Apply that plan (7 to add)?"
  ./with-secrets terraform -chdir=infra apply -input=false -auto-approve
  echo "   applied"
fi

step "2. WAL-G's keys in Bitwarden, and the Secret opportunity-wal in the cluster"
if on_server k3s kubectl -n opportunity get secret opportunity-wal >/dev/null 2>&1; then
  skip "the Secret is there"
else
  ask "Make the keys (if not in Bitwarden yet) and put the Secret in?"
  ./backups/pg-backup setup-secrets
  echo "   the Secret is in"
fi

step "3. Check"
on_server k3s kubectl -n opportunity get secret opportunity-wal
echo
echo "Ready: merge #24. When its deploy has finished:"
echo "  git latest && ./backups/pg-backup drill"
