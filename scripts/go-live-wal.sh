#!/usr/bin/env bash
# Makes the site's WAL archive ready for PostgreSQL to archive into: the bucket and its account
# (infra/'s module "wal", from #23), WAL-G's two keys in Bitwarden, and the Secret
# opportunity-wal in the cluster. Run it once, after #23 has merged and before #24 (the pod
# change, which this script ships with) does: the new pod needs the Secret to start. It doesn't
# need #24 merged, nor this checkout on main: it works in a temporary worktree of origin/main,
# so the apply is exactly what main holds. From this repository, signed in to gcloud and to
# Sustenaut's tailnet:
#
#   scripts/go-live-wal.sh
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

step "0. main has #23 (the archive's Terraform and backups/)"
git -C "$root" fetch -q origin main
main_tf=$(git -C "$root" show origin/main:infra/main.tf)
if [[ $main_tf != *'module "wal"'* ]] || ! git -C "$root" cat-file -e origin/main:backups/pg-backup.json 2>/dev/null; then
  echo "   origin/main doesn't have #23 yet: merge it first" >&2
  exit 1
fi
main=$(mktemp -d)
git -C "$root" worktree add -q --detach "$main" origin/main
trap 'git -C "$root" worktree remove --force "$main"' EXIT
cd "$main"
echo "   working in $main, at $(git rev-parse --short HEAD)"

step "1. The bucket sustenaut-opportunity-wal, its account and the chunk-delete role"
if gcloud storage buckets describe gs://sustenaut-opportunity-wal >/dev/null 2>&1; then
  skip "the bucket is there"
else
  ./with-secrets terraform -chdir=infra init -input=false >/dev/null
  ./with-secrets terraform -chdir=infra plan -input=false
  ask "Apply that plan (7 to add)?"
  ./with-secrets terraform -chdir=infra apply -input=false -auto-approve
fi

step "2. WAL-G's keys in Bitwarden, and the Secret opportunity-wal in the cluster"
if on_server k3s kubectl -n opportunity get secret opportunity-wal >/dev/null 2>&1; then
  skip "the Secret is there"
else
  ask "Make the keys (if not in Bitwarden yet) and put the Secret in?"
  ./backups/pg-backup setup-secrets
fi

step "3. Check"
on_server k3s kubectl -n opportunity get secret opportunity-wal
echo
echo "Ready: merge #24. When its deploy has finished, from an up-to-date main:"
echo "  git latest && ./backups/pg-backup drill"
