"""Deterministic evidence packet helpers for agent-facing planning."""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

from healthpilot.actions import build_action_queue_payload
from healthpilot.evidence import build_evidence_snapshot
from healthpilot.jsonio import load_json
from healthpilot.lifestyle import LIFESTYLE_SOURCE_FIELDS
from healthpilot.paths import expand_home, profiles_state_path
from healthpilot.profile import ProfileContext


INDEX_SUFFIXES = {".csv", ".json", ".md", ".txt", ".tsv"}
MAX_INDEXED_FILES_PER_SOURCE = 500
MAX_TEXT_LINES_PER_FILE = 240
MAX_SIGNAL_LINES = 16

SYMPTOM_SIGNAL_TERMS = (
    "pain",
    "fatigue",
    "tired",
    "sleep",
    "insomnia",
    "anxiety",
    "depression",
    "mood",
    "nausea",
    "bloating",
    "constipation",
    "diarrhea",
    "reflux",
    "gastritis",
    "palpitation",
    "dizzy",
    "headache",
    "flare",
    "worse",
    "improved",
)

MEDICATION_SIGNAL_TERMS = (
    "medication",
    "medicine",
    "supplement",
    "dose",
    "started",
    "stopped",
    "took",
    "taking",
    "trial",
    "ppi",
    "pantoprazole",
    "omeprazole",
    "magnesium",
    "vitamin",
    "b12",
    "d3",
    "iron",
    "psyllium",
    "creatine",
    "alcar",
    "carnitine",
)

CURRENT_STACK_HEADING_RE = re.compile(
    r"\b("
    r"current\s+(medication|medicine|supplement|medication\s*/\s*supplement)"
    r".{0,40}(stack|update|list)"
    r"|my\s+(medication|medicine|supplement).{0,30}(stack|list)\s+is\s+currently"
    r")\b",
    re.IGNORECASE,
)

DATE_HEADING_RE = re.compile(r"^#{1,6}\s+\d{4}[-/]\d{2}[-/]\d{2}\b")


def evidence_packet_path(repo_root: Path, profile_slug: str) -> Path:
    return profiles_state_path(repo_root, profile_slug, "evidence-packet.json")


def load_previous_evidence_packet(repo_root: Path, profile_slug: str) -> dict[str, Any] | None:
    path = evidence_packet_path(repo_root, profile_slug)
    if not path.exists():
        return None
    payload = load_json(path)
    return payload if isinstance(payload, dict) else None


def _utc_timestamp(value: float) -> str:
    return datetime.utcfromtimestamp(value).replace(microsecond=0).isoformat() + "Z"


def _clean(value: str, *, max_length: int = 220) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


def _read_text_lines(path: Path, *, max_lines: int = MAX_TEXT_LINES_PER_FILE) -> list[str]:
    lines: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                lines.append(line.rstrip("\n"))
                if len(lines) >= max_lines:
                    break
    except OSError:
        return []
    return lines


def _file_entry(path: Path, *, source_path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    try:
        relative_path = str(path.relative_to(source_path))
    except ValueError:
        relative_path = path.name
    return {
        "path": str(path),
        "relative_path": relative_path,
        "size_bytes": stat.st_size,
        "modified_at": _utc_timestamp(stat.st_mtime),
    }


def _iter_indexable_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in INDEX_SUFFIXES else []
    try:
        files = [
            item
            for item in path.rglob("*")
            if item.is_file() and item.suffix.lower() in INDEX_SUFFIXES
        ]
    except OSError:
        return []
    files.sort(key=lambda item: str(item))
    return files[:MAX_INDEXED_FILES_PER_SOURCE]


def _build_file_index(source_snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    file_index: dict[str, list[dict[str, Any]]] = {}
    for source_name, metadata in source_snapshot["sources"].items():
        if metadata.get("status") != "available" or not metadata.get("path"):
            file_index[source_name] = []
            continue
        source_path = expand_home(metadata["path"])
        entries = []
        for file_path in _iter_indexable_files(source_path):
            entry = _file_entry(file_path, source_path=source_path)
            if entry is not None:
                entries.append(entry)
        file_index[source_name] = entries
    return file_index


def _changed_files(
    current_index: dict[str, list[dict[str, Any]]],
    previous_packet: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    previous_index = (previous_packet or {}).get("file_index", {})
    if not isinstance(previous_index, dict) or not previous_index:
        return []

    changes: list[dict[str, Any]] = []
    source_names = sorted(set(current_index) | set(previous_index))
    for source_name in source_names:
        current_by_path = {
            item["path"]: item for item in current_index.get(source_name, [])
        }
        previous_items = previous_index.get(source_name, [])
        previous_by_path = {
            item["path"]: item for item in previous_items if isinstance(item, dict)
        }

        for path, item in sorted(current_by_path.items()):
            previous = previous_by_path.get(path)
            if previous is None:
                changes.append({"source_name": source_name, "change_type": "added", **item})
            elif (
                item.get("modified_at") != previous.get("modified_at")
                or item.get("size_bytes") != previous.get("size_bytes")
            ):
                changes.append({"source_name": source_name, "change_type": "modified", **item})

        for path, item in sorted(previous_by_path.items()):
            if path not in current_by_path:
                changes.append(
                    {
                        "source_name": source_name,
                        "change_type": "deleted",
                        "path": path,
                        "relative_path": item.get("relative_path", Path(path).name),
                        "size_bytes": item.get("size_bytes"),
                        "modified_at": item.get("modified_at"),
                    }
                )
    return changes


def _source_freshness(source_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        source_name: {
            "status": metadata.get("status", "unknown"),
            "path": metadata.get("path", ""),
            "latest_modified_at": metadata.get("latest_modified_at"),
            "sample": metadata.get("sample", []),
        }
        for source_name, metadata in source_snapshot["sources"].items()
    }


def _lab_entry(row: dict[str, str]) -> dict[str, Any]:
    is_abnormal = any(
        (row.get("is_above_limit", "").lower() in {"1", "true", "yes", "y"},
         row.get("is_below_limit", "").lower() in {"1", "true", "yes", "y"},
         row.get("review_needed", "").lower() in {"1", "true", "yes", "y"})
    )
    return {
        "date": (row.get("date") or "").strip(),
        "label": (
            row.get("lab_name")
            or row.get("lab_name_standardized")
            or row.get("raw_lab_name")
            or "unknown lab"
        ).strip(),
        "value": (row.get("value") or row.get("raw_value") or "").strip(),
        "unit": (row.get("lab_unit") or row.get("raw_lab_unit") or "").strip(),
        "reference_min": (row.get("reference_min") or row.get("raw_reference_min") or "").strip(),
        "reference_max": (row.get("reference_max") or row.get("raw_reference_max") or "").strip(),
        "is_abnormal": is_abnormal,
        "source_file": (row.get("source_file") or "").strip(),
        "page_number": (row.get("page_number") or "").strip(),
    }


def _summarize_labs(source_snapshot: dict[str, Any]) -> dict[str, Any]:
    metadata = source_snapshot["sources"].get("labs_path", {})
    if metadata.get("status") != "available" or not metadata.get("path"):
        return {"status": metadata.get("status", "not configured")}

    all_csv_path = expand_home(metadata["path"]) / "all.csv"
    if not all_csv_path.exists():
        return {"status": "available", "all_csv_present": False}

    latest_rows: deque[dict[str, Any]] = deque(maxlen=12)
    abnormal_rows: deque[dict[str, Any]] = deque(maxlen=16)
    dates: set[str] = set()
    marker_dates: dict[str, set[str]] = defaultdict(set)
    total_rows = 0
    try:
        with all_csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                total_rows += 1
                entry = _lab_entry(row)
                if entry["date"]:
                    dates.add(entry["date"])
                    marker_dates[entry["label"]].add(entry["date"])
                latest_rows.append(entry)
                if entry["is_abnormal"]:
                    abnormal_rows.append(entry)
    except OSError:
        return {"status": "available", "all_csv_present": True, "error": "Unable to read all.csv"}

    trend_candidates = [
        {"label": label, "date_count": len(values)}
        for label, values in sorted(marker_dates.items())
        if len(values) >= 2
    ]
    trend_candidates.sort(key=lambda item: (-item["date_count"], item["label"].lower()))
    return {
        "status": "available",
        "all_csv_path": str(all_csv_path),
        "all_csv_present": True,
        "total_rows": total_rows,
        "latest_lab_dates": sorted(dates)[-8:],
        "latest_results": list(latest_rows),
        "abnormal_markers": list(abnormal_rows),
        "trend_candidates": trend_candidates[:20],
    }


def _entry_date(path: Path) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else ""


def _matching_lines(path: Path, terms: tuple[str, ...], *, limit: int = MAX_SIGNAL_LINES) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    lowered_terms = tuple(term.lower() for term in terms)
    for line_number, line in enumerate(_read_text_lines(path), start=1):
        cleaned = _clean(line)
        if not cleaned or cleaned.startswith("#"):
            continue
        lowered = cleaned.lower()
        if any(term in lowered for term in lowered_terms):
            matches.append(
                {
                    "path": str(path),
                    "line": line_number,
                    "text": cleaned,
                }
            )
            if len(matches) >= limit:
                break
    return matches


def _strip_markdown_emphasis(value: str) -> str:
    return re.sub(r"[*_`]+", "", value).strip()


def _stack_heading_text(value: str) -> str:
    cleaned = re.sub(r"^\s*(?:#{1,6}\s+|[-*+]|\d+[.)])\s*", "", value)
    return _strip_markdown_emphasis(cleaned).rstrip(":")


def _markdown_list_item_text(value: str) -> str | None:
    match = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>.+?)\s*$", value)
    if not match:
        return None
    return _strip_markdown_emphasis(match.group("text"))


def _extract_current_stack_blocks(path: Path, *, limit: int = 3) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = _read_text_lines(path, max_lines=2000)
    for line_index, line in enumerate(lines):
        heading = _clean(line)
        if not heading or not CURRENT_STACK_HEADING_RE.search(heading):
            continue

        items: list[dict[str, Any]] = []
        for item_index, candidate in enumerate(lines[line_index + 1 : line_index + 41], start=line_index + 2):
            stripped = candidate.strip()
            if not stripped:
                if items:
                    break
                continue
            if DATE_HEADING_RE.match(stripped) or (
                stripped.startswith("#") and items
            ):
                break
            if CURRENT_STACK_HEADING_RE.search(stripped) and items:
                break

            item_text = _markdown_list_item_text(candidate)
            if item_text is None:
                if items:
                    break
                continue
            if CURRENT_STACK_HEADING_RE.search(item_text):
                continue
            items.append(
                {
                    "path": str(path),
                    "line": item_index,
                    "text": _clean(item_text),
                }
            )

        if items:
            blocks.append(
                {
                    "path": str(path),
                    "line": line_index + 1,
                    "heading": _stack_heading_text(heading),
                    "items": items,
                }
            )
            if len(blocks) >= limit:
                break
    return blocks


def _dedupe_current_stack_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for block in blocks:
        key = tuple(
            str(item.get("text", "")).strip().lower()
            for item in block.get("items", [])
            if item.get("text")
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(block)
    return deduped


def _recent_markdown_files(path: Path, pattern: str, *, limit: int = 8) -> list[Path]:
    try:
        files = sorted(path.glob(pattern))
    except OSError:
        return []
    return files[-limit:]


def _summarize_health_log(source_snapshot: dict[str, Any]) -> dict[str, Any]:
    metadata = source_snapshot["sources"].get("health_log_path", {})
    if metadata.get("status") != "available" or not metadata.get("path"):
        return {"status": metadata.get("status", "not configured")}

    source_path = expand_home(metadata["path"])
    entries_dir = source_path / "entries"
    health_log_path = source_path / "health_log.md"
    processed_files = _recent_markdown_files(entries_dir, "*.processed.md")
    raw_files = _recent_markdown_files(entries_dir, "*.raw.md", limit=5)
    signal_files = processed_files + raw_files
    unresolved_signals: list[dict[str, Any]] = []
    medication_mentions: list[dict[str, Any]] = []
    current_stack_blocks: list[dict[str, Any]] = []
    if health_log_path.exists():
        current_stack_blocks.extend(_extract_current_stack_blocks(health_log_path, limit=2))
    for path in signal_files:
        unresolved_signals.extend(_matching_lines(path, SYMPTOM_SIGNAL_TERMS, limit=4))
        medication_mentions.extend(_matching_lines(path, MEDICATION_SIGNAL_TERMS, limit=4))
        current_stack_blocks.extend(_extract_current_stack_blocks(path, limit=1))

    overview_signals = []
    if health_log_path.exists():
        overview_signals = _matching_lines(health_log_path, SYMPTOM_SIGNAL_TERMS, limit=8)
        medication_mentions.extend(_matching_lines(health_log_path, MEDICATION_SIGNAL_TERMS, limit=8))

    return {
        "status": "available",
        "health_log_path": str(health_log_path),
        "latest_entries": [
            {"date": _entry_date(path), "kind": path.suffixes[-2].lstrip("."), "path": str(path)}
            for path in processed_files + raw_files
        ],
        "unresolved_symptom_or_treatment_signal_lines": (unresolved_signals + overview_signals)[
            :MAX_SIGNAL_LINES
        ],
        "current_medication_supplement_stack": _dedupe_current_stack_blocks(
            current_stack_blocks
        )[:3],
        "medication_supplement_mentions_needing_review": medication_mentions[:MAX_SIGNAL_LINES],
    }


def _summarize_exams(source_snapshot: dict[str, Any]) -> dict[str, Any]:
    metadata = source_snapshot["sources"].get("exams_path", {})
    if metadata.get("status") != "available" or not metadata.get("path"):
        return {"status": metadata.get("status", "not configured")}
    source_path = expand_home(metadata["path"])
    summary_files = _iter_indexable_files(source_path)
    summary_files = [
        path
        for path in summary_files
        if path.suffix.lower() == ".md" and ("summary" in path.name.lower() or path.name.endswith(".md"))
    ]
    summary_files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    latest = []
    for path in summary_files[:8]:
        lines = [_clean(line) for line in _read_text_lines(path, max_lines=40)]
        excerpt = [line for line in lines if line][:5]
        latest.append({"path": str(path), "excerpt": excerpt})
    return {"status": "available", "latest_exam_summaries": latest}


def _summarize_genetics(source_snapshot: dict[str, Any]) -> dict[str, Any]:
    metadata = source_snapshot["sources"].get("genetics_23andme_path", {})
    if metadata.get("status") != "available":
        return {"status": metadata.get("status", "not configured")}
    details = metadata.get("details", {}) or {}
    return {
        "status": "available",
        "path": metadata.get("path", ""),
        "sample_rsids": details.get("sample_rsids", []),
    }


def _summarize_lifestyle(source_snapshot: dict[str, Any]) -> dict[str, Any]:
    lifestyle: dict[str, Any] = {}
    for source_name in sorted(LIFESTYLE_SOURCE_FIELDS):
        metadata = source_snapshot["sources"].get(source_name, {})
        lifestyle[source_name] = {
            "status": metadata.get("status", "not configured"),
            "path": metadata.get("path", ""),
            "latest_modified_at": metadata.get("latest_modified_at"),
            "summary": metadata.get("details", {}),
        }
    return lifestyle


def _is_stale(last_reviewed_at: str, source_freshness: dict[str, dict[str, Any]]) -> bool:
    if not last_reviewed_at:
        return True
    latest_values = [
        item.get("latest_modified_at")
        for item in source_freshness.values()
        if item.get("latest_modified_at")
    ]
    return any(str(value) > last_reviewed_at for value in latest_values)


def _issue_memory(
    *,
    profile_slug: str,
    profile_name: str,
    generated_at: str,
    issues: dict[str, dict[str, Any]],
    source_freshness: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    actions = build_action_queue_payload(
        profile_slug=profile_slug,
        profile_name=profile_name,
        generated_at=generated_at,
        issues=issues,
    )
    active_issues = []
    stale_or_open_action_gaps = []
    for slug, issue in sorted(issues.items()):
        if issue["status"] not in {"active", "monitoring"}:
            continue
        linked_sources = issue.get("linked_sources", [])
        active_issues.append(
            {
                "slug": slug,
                "title": issue["title"],
                "status": issue["status"],
                "confidence_frame": issue["confidence_frame"],
                "last_reviewed_at": issue["last_reviewed_at"],
                "source_citations": linked_sources,
            }
        )
        gap_reasons = []
        if not linked_sources:
            gap_reasons.append("missing source citations")
        if _is_stale(issue.get("last_reviewed_at", ""), source_freshness):
            gap_reasons.append("newer configured source data exists")
        if gap_reasons:
            stale_or_open_action_gaps.append(
                {"slug": slug, "title": issue["title"], "gap_reasons": gap_reasons}
            )

    return {
        "active_issues": active_issues,
        "ranked_actions": actions["actions"],
        "stale_or_open_action_gaps": stale_or_open_action_gaps,
    }


def build_evidence_packet(
    *,
    repo_root: Path,
    profile_context: ProfileContext,
    generated_at: str,
    issues: dict[str, dict[str, Any]],
    previous_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_snapshot = build_evidence_snapshot(profile_context, generated_at=generated_at)
    file_index = _build_file_index(source_snapshot)
    source_freshness = _source_freshness(source_snapshot)
    changed_files = _changed_files(file_index, previous_packet)

    source_name_counts = Counter(item["source_name"] for item in changed_files)
    return {
        "profile_slug": profile_context.slug,
        "profile_name": profile_context.cache_payload["profile_name"],
        "profile_path": profile_context.cache_payload["profile_path"],
        "generated_at": generated_at,
        "source_snapshot": source_snapshot,
        "source_freshness": source_freshness,
        "changed_files_since_last_run": changed_files,
        "changed_file_counts": dict(sorted(source_name_counts.items())),
        "labs": _summarize_labs(source_snapshot),
        "health_log": _summarize_health_log(source_snapshot),
        "exams": _summarize_exams(source_snapshot),
        "genetics": _summarize_genetics(source_snapshot),
        "lifestyle": _summarize_lifestyle(source_snapshot),
        "issue_memory": _issue_memory(
            profile_slug=profile_context.slug,
            profile_name=profile_context.cache_payload["profile_name"],
            generated_at=generated_at,
            issues=issues,
            source_freshness=source_freshness,
        ),
        "file_index": file_index,
    }
