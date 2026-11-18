"""Steps for features/wal-credential.feature: the WAL archive's keyless credential."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pytest_bdd import parsers, scenarios, when

from manifests import ROOT, credential, documents, found, mounts_api_token

scenarios(str(Path(__file__).resolve().parent / "features" / "wal-credential.feature"))


@when(parsers.parse('the credential in "{path}" is read'))
def credential_read(ctx, path):
    ctx.attempt(lambda: credential(path))


@when(parsers.parse('the WAL settings in "{path}" are read'))
def settings_read(ctx, path):
    ctx.attempt(lambda: json.loads((ROOT / path).read_text(encoding="utf-8"))["wal"])


@when(parsers.parse('the restore account id in "{path}" is read'))
def restore_account(ctx, path):
    ctx.attempt(lambda: re.search(r'restore_account_id = "([^"]+)"', (ROOT / path).read_text(encoding="utf-8"))[1])


def statefulset(path: str) -> dict:
    return next(d for d in documents(path) if d["kind"] == "StatefulSet")["spec"]["template"]["spec"]


@when(parsers.parse('the StatefulSet in "{path}" is read'))
def statefulset_read(ctx, path):
    def read():
        spec = statefulset(path)
        return spec | {"its account mounts an API token": mounts_api_token(spec["serviceAccountName"])}
    ctx.attempt(read)


@when(parsers.parse('the {name} container of the StatefulSet in "{path}" is read'))
def container_read(ctx, name, path):
    def read():
        spec = statefulset(path)
        (volume,) = [v for v in spec["volumes"] if (v.get("configMap") or {}).get("name") == "wal-google-credential"]
        return found(spec, next(c for c in spec["containers"] if c["name"] == name), volume["name"])
    ctx.attempt(read)
