Feature: PostgreSQL reaches its WAL archive with no key
  The database and its wal-g sidecar read the external_account credential in
  k8s/wal-google-credential.yaml, which trades the pod's projected token for
  sustenaut-opportunity-wal through Workload Identity. A mismatch between the provider,
  the token's audience and the credential's fails only at run time, as Google's
  STS refusing the token, so the manifests are held to one another here.

  Scenario: The credential acts as the archive's account, at the provider's audience
    When the credential in "k8s/wal-google-credential.yaml" is read
    Then the result's "type" is "external_account"
    And the result's "audience" is "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s"
    And the result's "credential_source.file" is "/var/run/secrets/google/token"
    And the result's "service_account_impersonation_url" is "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/sustenaut-opportunity-wal@sustenaut.iam.gserviceaccount.com:generateAccessToken"
    And the result's "configmap" is "wal-google-credential"

  Scenario: pg-backup.json names that account, its read-only restore account, the ServiceAccount and the ConfigMap
    When the WAL settings in "backups/pg-backup.json" are read
    Then the result's "account" is "sustenaut-opportunity-wal@sustenaut.iam.gserviceaccount.com"
    And the result's "restore_account" is "sustenaut-opportunity-wal-read@sustenaut.iam.gserviceaccount.com"
    And the result's "serviceaccount" is "postgres"
    And the result's "credential" is "wal-google-credential"
    And the result does not include "gcs_key_secret"

  Scenario: The read-only restore account is the one infra/main.tf makes
    When the restore account id in "infra/main.tf" is read
    Then the result is "sustenaut-opportunity-wal-read"

  Scenario: The StatefulSet runs as postgres, with no API token and no key
    When the StatefulSet in "k8s/postgres.yaml" is read
    Then the result's "serviceAccountName" is "postgres"
    And the result's "automountServiceAccountToken" is "false"
    And the result's "its account mounts an API token" is "false"
    And the result's "volumes" is "[{"name": "google-token", "projected": {"sources": [{"serviceAccountToken": {"audience": "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s", "path": "token", "expirationSeconds": 3600}}]}}, {"name": "wal-google-credential", "configMap": {"name": "wal-google-credential"}}, {"name": "walg-state", "emptyDir": {}}]"

  Scenario Outline: Each container reads the token and the credential where they are
    When the <container> container of the StatefulSet in "k8s/postgres.yaml" is read
    Then the result's "token at" is "/var/run/secrets/google/token"
    And the result's "the credential at" is "/etc/wal-google/credential.json"
    And the result's "GOOGLE_APPLICATION_CREDENTIALS" is "/etc/wal-google/credential.json"

    Examples:
      | container |
      | postgres  |
      | wal-g     |
