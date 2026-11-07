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

# Where every change to the site's database goes, as it is made: PostgreSQL's write-ahead log,
# archived by WAL-G within a minute (k8s/postgres.yaml), with a base backup each night, so the
# database can be restored to any moment in the last 14 days. The nightly dumps above stay as
# a second copy that does not depend on PostgreSQL's version or on WAL-G.
# Sustenaut/pg-backup's module: the bucket, its add-and-read account (which may delete only its
# own upload chunks), and deletion by age. `./backups/pg-backup setup-secrets` makes the keys.
module "wal" {
  source = "github.com/Sustenaut/pg-backup//terraform/wal-archive?ref=v0.2.0"

  project              = local.gcp.project
  region               = local.gcp.region
  bucket               = "${local.gcp.project}-opportunity-wal"
  prefix               = "opportunity"
  account_id           = "sustenaut-opportunity-wal"
  account_display_name = "Sustenaut opportunity WAL archive"
  account_description  = "WAL-G on the Hetzner k3s server: archives the opportunity site's write-ahead log and nightly base backups into the opportunity-wal bucket. Creates and reads; deletes only its own upload chunks."
  role_id              = "walChunkDeleteOpportunity" # auth's archive has walChunkDelete
}
