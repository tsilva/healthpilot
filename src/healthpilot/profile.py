"""Runtime profile loading and source validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from healthpilot.paths import expand_home, profiles_dir

SOURCE_FIELDS = (
    "labs_path",
    "exams_path",
    "health_log_path",
    "genetics_23andme_path",
    "schedule_md_path",
    "nutrition_md_path",
    "exercise_md_path",
    "lifestyle_constraints_md_path",
)


@dataclass(slots=True)
class ProfileContext:
    slug: str
    path: Path
    data: dict[str, Any]
    cache_payload: dict[str, Any]


def discover_profile_path(profile_ref: str, *, home_dir: Path) -> Path:
    raw_path = Path(profile_ref).expanduser()
    if raw_path.exists():
        return raw_path.resolve()

    candidate = profiles_dir(home_dir).joinpath(f"{profile_ref}.yaml")
    if candidate.exists():
        return candidate.resolve()

    raise FileNotFoundError(
        f"Could not resolve profile '{profile_ref}'. Checked {raw_path} and {candidate}."
    )


def _sample_path(path: Path) -> list[str]:
    if path.is_dir():
        try:
            return sorted(entry.name for entry in path.iterdir())[:5]
        except PermissionError:
            return []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            first_line = handle.readline().strip()
            return [first_line] if first_line else []
    except OSError:
        return []


def classify_source(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {"path": "", "status": "not configured", "sample": []}

    path = expand_home(path_value)
    if not path.exists():
        return {"path": str(path), "status": "missing", "sample": []}
    if not os.access(path, os.R_OK):
        return {"path": str(path), "status": "unreadable", "sample": []}
    return {"path": str(path), "status": "available", "sample": _sample_path(path)}


def load_profile_context(profile_ref: str, *, home_dir: Path) -> ProfileContext:
    profile_path = discover_profile_path(profile_ref, home_dir=home_dir)
    raw_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    slug = profile_path.stem
    data_sources = raw_data.get("data_sources", {})
    source_status = {
        field: classify_source(data_sources.get(field))
        for field in SOURCE_FIELDS
    }
    selfdecode = data_sources.get("selfdecode", {}) or {}
    cache_payload = {
        "profile_slug": slug,
        "profile_name": raw_data.get("name", slug),
        "profile_path": str(profile_path),
        "demographics": raw_data.get("demographics", {}),
        "sources": source_status,
        "selfdecode": {
            "enabled": bool(selfdecode.get("enabled")),
            "profile_id_configured": bool(selfdecode.get("profile_id")),
            "jwt_token_configured": bool(selfdecode.get("jwt_token")),
        },
    }
    return ProfileContext(
        slug=slug,
        path=profile_path,
        data=raw_data,
        cache_payload=cache_payload,
    )
