"""Deterministic evidence snapshot helpers for parsed source folders."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from healthpilot.lifestyle import LIFESTYLE_SOURCE_FIELDS, summarize_markdown_source
from healthpilot.paths import expand_home
from healthpilot.profile import ProfileContext


def _utc_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat()


def _latest_mtime(path: Path) -> float | None:
    try:
        if path.is_dir():
            mtimes = [entry.stat().st_mtime for entry in path.iterdir()]
            return max(mtimes, default=path.stat().st_mtime)
        return path.stat().st_mtime
    except OSError:
        return None


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _clean_line(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _recent_files(path: Path, *, limit: int = 5) -> list[str]:
    try:
        files = [entry for entry in path.iterdir()]
    except OSError:
        return []
    files.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    return [entry.name for entry in files[:limit]]


def _summarize_labs(source_path: Path) -> dict[str, Any]:
    all_csv_path = source_path / "all.csv"
    if not all_csv_path.exists():
        return {
            "all_csv_present": False,
            "recent_results": [],
            "recent_abnormal_results": [],
        }

    results: list[dict[str, str]] = []
    abnormal_results: list[dict[str, str]] = []
    total_rows = 0

    try:
        with all_csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                total_rows += 1
                date = (row.get("date") or "").strip()
                label = (
                    row.get("lab_name")
                    or row.get("lab_name_standardized")
                    or row.get("raw_lab_name")
                    or "unknown lab"
                ).strip()
                value = (row.get("value") or row.get("raw_value") or "").strip()
                unit = (row.get("lab_unit") or row.get("raw_lab_unit") or "").strip()
                entry = {
                    "date": date,
                    "label": label,
                    "value": value,
                    "unit": unit,
                }
                results.append(entry)
                if any(
                    (
                        _truthy(row.get("is_above_limit")),
                        _truthy(row.get("is_below_limit")),
                        _truthy(row.get("review_needed")),
                    )
                ):
                    abnormal_results.append(entry)
    except OSError:
        return {
            "all_csv_present": True,
            "recent_results": [],
            "recent_abnormal_results": [],
            "error": "Unable to read all.csv",
        }

    results.sort(key=lambda item: (item["date"], item["label"].lower()))
    abnormal_results.sort(key=lambda item: (item["date"], item["label"].lower()))

    return {
        "all_csv_present": True,
        "total_rows": total_rows,
        "recent_results": results[-5:],
        "recent_abnormal_results": abnormal_results[-5:],
    }


def _summarize_health_log(source_path: Path) -> dict[str, Any]:
    health_log_path = source_path / "health_log.md"
    headline = None
    if health_log_path.exists():
        try:
            with health_log_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    headline = _clean_line(line)
                    if headline:
                        break
        except OSError:
            headline = None

    entries_dir = source_path / "entries"
    processed_entries = []
    raw_entries = []
    if entries_dir.exists() and entries_dir.is_dir():
        processed_entries = sorted(entries_dir.glob("*.processed.md"))[-5:]
        raw_entries = sorted(entries_dir.glob("*.raw.md"))[-5:]

    return {
        "headline": headline,
        "recent_processed_entries": [path.name for path in processed_entries],
        "recent_raw_entries": [path.name for path in raw_entries],
    }


def _summarize_exams(source_path: Path) -> dict[str, Any]:
    return {
        "recent_files": _recent_files(source_path),
    }


def _summarize_genetics(source_path: Path) -> dict[str, Any]:
    rsids: list[str] = []
    try:
        with source_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.startswith("#"):
                    continue
                rsid = line.split("\t", 1)[0].strip()
                if not rsid:
                    continue
                rsids.append(rsid)
                if len(rsids) >= 5:
                    break
    except OSError:
        return {"sample_rsids": []}
    return {"sample_rsids": rsids}


def _build_source_snapshot(name: str, metadata: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(metadata)
    path_value = metadata.get("path") or ""
    if not path_value or metadata.get("status") != "available":
        snapshot["details"] = {}
        snapshot["latest_modified_at"] = None
        return snapshot

    source_path = expand_home(path_value)
    snapshot["latest_modified_at"] = _utc_timestamp(_latest_mtime(source_path))

    if name == "labs_path":
        snapshot["details"] = _summarize_labs(source_path)
    elif name == "health_log_path":
        snapshot["details"] = _summarize_health_log(source_path)
    elif name == "exams_path":
        snapshot["details"] = _summarize_exams(source_path)
    elif name == "genetics_23andme_path":
        snapshot["details"] = _summarize_genetics(source_path)
    elif name in LIFESTYLE_SOURCE_FIELDS:
        snapshot["details"] = summarize_markdown_source(source_path)
    else:
        snapshot["details"] = {}

    return snapshot


def build_evidence_snapshot(
    profile_context: ProfileContext,
    *,
    generated_at: str,
) -> dict[str, Any]:
    sources = {
        name: _build_source_snapshot(name, metadata)
        for name, metadata in profile_context.cache_payload["sources"].items()
    }
    return {
        "profile_slug": profile_context.slug,
        "profile_name": profile_context.cache_payload["profile_name"],
        "profile_path": profile_context.cache_payload["profile_path"],
        "generated_at": generated_at,
        "demographics": profile_context.cache_payload["demographics"],
        "sources": sources,
    }
