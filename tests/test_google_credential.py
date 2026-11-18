"""Steps for features/google-credential.feature: the backup reaches Cloud Storage with no key.
The Cloud SDK reads the external_account credential in k8s/google-credential.yaml, whose
audience must be the projected token's and the services pool's provider."""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import parsers, scenarios, when

from manifests import credential, documents, found, mounts_api_token, token_volume

scenarios(str(Path(__file__).resolve().parent / "features" / "google-credential.feature"))


@when(parsers.parse('the credential in "{path}" is read'))
def credential_read(ctx, path):
    ctx.attempt(lambda: credential(path))


@when(parsers.parse('the backup CronJob in "{path}" is read'))
def cronjob_read(ctx, path):
    def read():
        (cronjob,) = documents(path)
        spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        (upload,) = spec["containers"]
        return {"serviceAccountName": spec["serviceAccountName"],
                "automountServiceAccountToken": spec["automountServiceAccountToken"],
                "its account mounts an API token": mounts_api_token(spec["serviceAccountName"]),
                "token audience": token_volume(spec)["audience"],
                "uses --key-file": "--key-file" in " ".join(upload["command"]),
                **found(spec, upload, "google-credential")}
    ctx.attempt(read)
