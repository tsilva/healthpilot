"""SelfDecode genotype lookup and repo-local caching."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from healthpilot.jsonio import load_json, write_json
from healthpilot.paths import profiles_state_path
from healthpilot.profile import ProfileContext

SELFDECODE_BASE_URL = "https://selfdecode.com"


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def genotype_cache_path(repo_root: Path, profile_slug: str) -> Path:
    return profiles_state_path(repo_root, profile_slug, "selfdecode-genotypes.json")


def load_genotype_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"items": {}}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {"items": {}}
    payload.setdefault("items", {})
    return payload


def normalize_rsids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rsids: list[str] = []
    for value in values:
        for raw in value.split(","):
            rsid = raw.strip()
            if not rsid or rsid in seen:
                continue
            seen.add(rsid)
            rsids.append(rsid)
    return rsids


def normalize_jwt_token(token: str | None) -> str:
    if not token:
        return ""
    token = token.strip()
    if token.lower().startswith("jwt "):
        return token[4:].strip()
    return token


def profile_selfdecode_config(profile_context: ProfileContext) -> dict[str, Any]:
    data_sources = profile_context.data.get("data_sources", {}) or {}
    return data_sources.get("selfdecode", {}) or {}


def resolve_selfdecode_token(profile_context: ProfileContext, explicit_token: str | None) -> str:
    _ = profile_context
    return normalize_jwt_token(explicit_token) or normalize_jwt_token(os.environ.get("SELFDECODE_JWT"))


def fetch_selfdecode_genotypes(
    *,
    profile_id: str,
    rsids: list[str],
    jwt_token: str,
    timeout_seconds: int = 30,
) -> dict[str, dict[str, Any]]:
    if not profile_id:
        raise ValueError("SelfDecode profile_id is not configured for this profile.")
    if not jwt_token:
        raise ValueError("A SelfDecode JWT token is required for uncached genotype lookups.")
    if not rsids:
        return {}

    query = urllib.parse.urlencode({"profile_id": profile_id, "rsid": ",".join(rsids)})
    url = f"{SELFDECODE_BASE_URL}/service/health-analysis/genes/genotype/?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"JWT {normalize_jwt_token(jwt_token)}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SelfDecode genotype lookup failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"SelfDecode genotype lookup failed: {exc}") from exc

    now = utc_now()
    returned: dict[str, dict[str, Any]] = {}
    for row in payload:
        rsid = row.get("rsid")
        if not rsid:
            continue
        genotypes = row.get("genotypes") or []
        returned[rsid] = {
            "rsid": rsid,
            "status": "available",
            "genotype": "".join(genotypes),
            "genotypes": genotypes,
            "variant_ids": row.get("variant_ids") or [],
            "profile_id": row.get("profile_id") or profile_id,
            "source": "selfdecode",
            "fetched_at": now,
        }

    for rsid in rsids:
        returned.setdefault(
            rsid,
            {
                "rsid": rsid,
                "status": "no_result",
                "genotype": "NO_RESULT",
                "genotypes": [],
                "variant_ids": [],
                "profile_id": profile_id,
                "source": "selfdecode",
                "fetched_at": now,
            },
        )
    return returned


def update_genotype_cache(
    *,
    repo_root: Path,
    profile_context: ProfileContext,
    fetched_items: dict[str, dict[str, Any]],
) -> Path:
    path = genotype_cache_path(repo_root, profile_context.slug)
    payload = load_genotype_cache(path)
    items = dict(payload.get("items", {}))
    items.update(fetched_items)
    write_json(
        path,
        {
            "profile_slug": profile_context.slug,
            "profile_name": profile_context.cache_payload["profile_name"],
            "source": "selfdecode",
            "updated_at": utc_now(),
            "items": items,
        },
    )
    return path
