# Where the opportunity site's nightly database dumps go: a bucket in Finland, kept 30
# days, written by an account that can create objects and nothing else. The site itself
# runs on the Sustenaut k3s server, whose Terraform, like the site's DNS record, is
# Sustenaut/shared-infra's. This stack does not read that state.
#
# The account's key is not here, so no state holds it: `pubkit service-account-key
# create` puts it in Bitwarden as opportunity-backup-gcs-key, and push-secrets.sh gives
# it to the cluster.

locals {
  gcp = jsondecode(file("${path.module}/../pubkit.json")).hosting.providers["google-cloud"]
}

module "backups" {
  source = "github.com/Sustenaut/pubkit//terraform/backup-bucket?ref=v0.26.0"

  bucket  = "${local.gcp.project}-opportunity-backups"
  project = local.gcp.project
  region  = local.gcp.region

  account_id           = "sustenaut-opportunity-backup"
  account_display_name = "Sustenaut opportunity backups"
  account_description  = "Writes the opportunity site's nightly PostgreSQL dumps from the Hetzner k3s server into the opportunity-backups bucket."
  create_key           = false
}
