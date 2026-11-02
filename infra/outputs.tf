output "backups" {
  description = "The backup bucket, and the account that writes to it."
  value = {
    bucket  = module.backups.bucket
    account = module.backups.account
  }
}
