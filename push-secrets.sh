#!/usr/bin/env bash
# Puts the opportunity site's secrets into the cluster on the Sustenaut k3s
# server: the Secret opportunity-secrets, the image pull secret ghcr-pull, and the
# network policy (k8s/admin/), all in namespace opportunity. Run it from the
# repository root through with-secrets, after the first terraform apply, whenever
# a secret changes, and whenever var.team changes:
#
#   ./with-secrets opportunity-site/push-secrets.sh
#
# From Bitwarden (which with-secrets exports in upper case):
#   opportunity-db-password                 the site's PostgreSQL password
#   opportunity-cookie-secret               oauth2-proxy's cookie secret (32 random bytes, base64)
#   opportunity-github-app-id               the GitHub App that opens pull requests
#   opportunity-github-app-key              its private key (PEM)
#   opportunity-github-installation-id      its installation on schryer/business-plan
#   opportunity-ghcr-pull-token             a token with read:packages, to pull the private image
# From Terraform: the team (var.team), the owner, and the backup key.
# Not here: the sign-in client oauth2-proxy uses (the Secret opportunity-oidc), which
# register-client.sh registers with auth.sustenaut.eu and puts in on the server.
# They travel to the server inside the SSH connection, never on a command line.
# The pods read them at start: after a change, restart them with
#   ssh root@sustenaut k3s kubectl -n opportunity rollout restart deployment/app deployment/oauth2-proxy
set -euo pipefail
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

for name in OPPORTUNITY_DB_PASSWORD OPPORTUNITY_COOKIE_SECRET OPPORTUNITY_GITHUB_APP_ID \
  OPPORTUNITY_GITHUB_APP_KEY OPPORTUNITY_GITHUB_INSTALLATION_ID OPPORTUNITY_GHCR_PULL_TOKEN; do
  if [ -z "${!name:-}" ]; then
    echo "$name is not set: run this through ./with-secrets, and check the secret is in Bitwarden." >&2
    exit 1
  fi
done

# SSH reaches the server over Sustenaut's tailnet only (be signed in to it).
server=$(terraform -chdir="$root/infra" output -json sustenaut_server | jq -r .ssh_host)
site=$(terraform -chdir="$root/infra" output -json opportunity)
team=$(jq -r '.team | join(",")' <<<"$site")
team_emails=$(jq -r '.team[]' <<<"$site")
owner=$(jq -r .owner <<<"$site")
backup_key=$(terraform -chdir="$root/infra" output -raw opportunity_backup_key) # already base64
b64() { printf '%s' "$1" | base64 -w0; }
pull=$(printf '{"auths":{"ghcr.io":{"auth":"%s"}}}' "$(b64 "schryer:$OPPORTUNITY_GHCR_PULL_TOKEN")")

# shellcheck disable=SC2087 # expanded here on purpose: the values go in the SSH stream
ssh "root@$server" 'k3s kubectl apply -f -' <<YAML
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: opportunity-secrets
  namespace: opportunity
data:
  db-password: $(b64 "$OPPORTUNITY_DB_PASSWORD")
  cookie-secret: $(b64 "$OPPORTUNITY_COOKIE_SECRET")
  github-app-id: $(b64 "$OPPORTUNITY_GITHUB_APP_ID")
  github-app-key: $(b64 "$OPPORTUNITY_GITHUB_APP_KEY")
  github-installation-id: $(b64 "$OPPORTUNITY_GITHUB_INSTALLATION_ID")
  team: $(b64 "$team")
  team-emails: $(b64 "$team_emails")
  owner: $(b64 "$owner")
  backup-gcs-key: $backup_key
---
apiVersion: v1
kind: Secret
type: kubernetes.io/dockerconfigjson
metadata:
  name: ghcr-pull
  namespace: opportunity
data:
  .dockerconfigjson: $(b64 "$pull")
---
$(cat "$root/opportunity-site/k8s/admin/network-policy.yaml")
YAML
