Feature: The backup's Google credential
  The external_account credential the backup reads names one audience: the projected token's
  and the services pool's provider. A mismatch fails only at run time, as Google's STS
  refusing the token.

  Scenario: The backup's credential acts as its account, at the provider's audience
    When the credential in "k8s/google-credential.yaml" is read
    Then the result's "type" is "external_account"
    And the result's "audience" is "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s"
    And the result's "credential_source.file" is "/var/run/secrets/google/token"
    And the result's "service_account_impersonation_url" is "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/sustenaut-opportunity-backup@sustenaut.iam.gserviceaccount.com:generateAccessToken"

  Scenario: The backup runs as backup, with no API token, its token the provider's audience
    When the backup CronJob in "k8s/backup.yaml" is read
    Then the result's "serviceAccountName" is "backup"
    And the result's "automountServiceAccountToken" is "false"
    And the result's "its account mounts an API token" is "false"
    And the result's "token audience" is "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s"

  Scenario: The backup finds the token where the credential reads it, and uses no key file
    When the backup CronJob in "k8s/backup.yaml" is read
    Then the result's "token at" is "/var/run/secrets/google/token"
    And the result's "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE" is "/etc/google/credential.json"
    And the result's "the credential at" is "/etc/google/credential.json"
    And the result's "uses --key-file" is "false"
