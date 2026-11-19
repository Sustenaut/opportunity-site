"""Reading the manifests in k8s/, as Kubernetes and Google read them: the credential a
ConfigMap holds, a pod's spec, and where each container finds its token and credential."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def documents(path: str) -> list[dict]:
    return [d for d in yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8")) if d]


def credential(path: str) -> dict:
    (configmap,) = documents(path)
    return json.loads(configmap["data"]["credential.json"]) | {"configmap": configmap["metadata"]["name"]}


def mounts_api_token(account: str) -> bool:
    accounts = {d["metadata"]["name"]: d for d in documents("k8s/service-accounts.yaml")}
    return accounts[account].get("automountServiceAccountToken") is not False


def token_volume(spec: dict) -> dict:
    (volume,) = [v for v in spec["volumes"] if "projected" in v]
    (source,) = volume["projected"]["sources"]
    return {"name": volume["name"], **source["serviceAccountToken"]}


def found(spec: dict, container: dict, credential_volume: str) -> dict:
    """Where the container finds the projected token and the credential's ConfigMap."""
    mounts = {m["name"]: m["mountPath"] for m in container["volumeMounts"]}
    token = token_volume(spec)
    return {"token at": f"{mounts[token['name']]}/{token['path']}",
            "the credential at": f"{mounts[credential_volume]}/credential.json",
            **{e["name"]: e.get("value") for e in container.get("env", [])}}
