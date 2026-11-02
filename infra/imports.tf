# These were made by Sustenaut/shared-infra, which forgets them once this stack has
# them. Nothing is created. Remove this file once both stacks have been applied.

import {
  to = module.backups.google_storage_bucket.backups
  id = "sustenaut-opportunity-backups"
}

import {
  to = module.backups.google_service_account.writer
  id = "projects/sustenaut/serviceAccounts/sustenaut-opportunity-backup@sustenaut.iam.gserviceaccount.com"
}

import {
  to = module.backups.google_storage_bucket_iam_member.writer
  id = "b/sustenaut-opportunity-backups roles/storage.objectCreator serviceAccount:sustenaut-opportunity-backup@sustenaut.iam.gserviceaccount.com"
}
