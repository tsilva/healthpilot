"""Markdown lifestyle source helpers and draft daily plan rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from healthpilot.paths import expand_home


LIFESTYLE_SOURCE_FIELDS = {
    "schedule_md_path",
    "nutrition_md_path",
    "exercise_md_path",
    "lifestyle_constraints_md_path",
}

SNIPPET_TERMS = (
    "wake",
    "sleep",
    "meal",
    "supplement",
    "medication",
    "gym",
    "workout",
    "exercise",
    "target weight",
    "weight",
    "avoid",
    "trigger",
    "constraint",
    "fixed",
    "cannot",
)

TIME_RANGE_RE = re.compile(
    r"(?P<start>\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*"
    r"(?:-|to|until|through)\s*"
    r"(?P<end>\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Interval:
    label: str
    start: int
    end: int

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


def _read_markdown_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def _clean(value: str, *, max_length: int = 180) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


def summarize_markdown_source(path: Path) -> dict[str, Any]:
    lines = _read_markdown_lines(path)
    first_lines: list[str] = []
    headings: list[str] = []
    snippets: list[str] = []

    for line in lines:
        cleaned = _clean(line)
        if not cleaned:
            continue
        if len(first_lines) < 3:
            first_lines.append(cleaned)
        if cleaned.startswith("#"):
            headings.append(cleaned.lstrip("#").strip())
        if any(term in cleaned.lower() for term in SNIPPET_TERMS):
            snippets.append(cleaned)

    return {
        "line_count": len(lines),
        "first_lines": first_lines,
        "headings": headings[:12],
        "relevant_snippets": snippets[:12],
    }


def _source_text(evidence_snapshot: dict[str, Any], source_name: str) -> str:
    source = evidence_snapshot["sources"].get(source_name, {})
    if source.get("status") != "available":
        return ""
    path_value = source.get("path") or ""
    if not path_value:
        return ""
    try:
        return expand_home(path_value).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _strip_list_marker(value: str) -> str:
    return re.sub(r"^\s*(?:[-*]|\d+\.)\s*", "", value).strip()


def _split_constraint_items(value: str) -> list[str]:
    if ":" in value:
        value = value.split(":", 1)[1]
    items = re.split(r",|;|\band\b", value, flags=re.IGNORECASE)
    return [
        re.sub(r"[`*_()[\].]", "", item).strip().lower()
        for item in items
        if 2 <= len(re.sub(r"[`*_()[\].]", "", item).strip()) <= 48
    ]


def _blocked_food_terms(constraints_text: str) -> list[str]:
    blocked: list[str] = []
    for raw_line in constraints_text.splitlines():
        line = _strip_list_marker(raw_line)
        lowered = line.lower()
        if not any(
            marker in lowered
            for marker in (
                "foods to avoid",
                "avoid:",
                "symptom-trigger",
                "trigger foods",
                "will not reliably eat",
                "do not eat",
                "do not include",
                "dislike",
            )
        ):
            continue
        blocked.extend(_split_constraint_items(line))

    deduped: list[str] = []
    for item in blocked:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _candidate_lines(text: str, *, blocked_terms: list[str] | None = None) -> tuple[list[str], int]:
    blocked_terms = blocked_terms or []
    candidates: list[str] = []
    removed = 0

    for raw_line in text.splitlines():
        line = _clean(_strip_list_marker(raw_line), max_length=220)
        if not line or line.startswith("#") or set(line) <= {"-", "="}:
            continue
        lowered = line.lower()
        if any(term and term in lowered for term in blocked_terms):
            removed += 1
            continue
        if len(candidates) < 8:
            candidates.append(line)

    return candidates, removed


def _minutes(value: str) -> int | None:
    raw = value.strip().lower().replace(" ", "")
    match = re.fullmatch(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?(?P<ampm>am|pm)?", raw)
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or "0")
    ampm = match.group("ampm")
    if hour > 23 or minute > 59:
        return None
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return hour * 60 + minute


def _intervals_from_text(text: str, *, required_terms: tuple[str, ...]) -> list[Interval]:
    intervals: list[Interval] = []
    for raw_line in text.splitlines():
        line = _clean(raw_line)
        lowered = line.lower()
        if not any(term in lowered for term in required_terms):
            continue
        for match in TIME_RANGE_RE.finditer(line):
            start = _minutes(match.group("start"))
            end = _minutes(match.group("end"))
            if start is None or end is None:
                continue
            if end <= start:
                end += 24 * 60
            intervals.append(Interval(label=line, start=start, end=end))
    return intervals


def _exercise_conflicts(schedule_text: str, exercise_text: str, constraints_text: str) -> list[str]:
    conflicts: list[str] = []
    fixed_schedule = _intervals_from_text(
        schedule_text + "\n" + constraints_text,
        required_terms=("fixed", "work", "sleep", "cannot move", "busy"),
    )
    exercise_intervals = _intervals_from_text(
        exercise_text,
        required_terms=("gym", "workout", "training", "exercise", "run", "lift"),
    )
    for exercise in exercise_intervals:
        if any(exercise.overlaps(block) for block in fixed_schedule):
            conflicts.append(
                "Exercise template time overlaps a fixed schedule block; regenerate around a movable window."
            )
            break

    lowered_constraints = constraints_text.lower()
    if any(marker in lowered_constraints for marker in ("no available workout window", "no workout window", "workout impossible")):
        conflicts.append("Lifestyle constraints say no workout window is available for this template.")

    return conflicts


def render_daily_plan(
    *,
    profile_slug: str,
    profile_name: str,
    generated_at: str,
    target_date: str,
    evidence_snapshot: dict[str, Any],
) -> str:
    schedule_text = _source_text(evidence_snapshot, "schedule_md_path")
    nutrition_text = _source_text(evidence_snapshot, "nutrition_md_path")
    exercise_text = _source_text(evidence_snapshot, "exercise_md_path")
    constraints_text = _source_text(evidence_snapshot, "lifestyle_constraints_md_path")

    blocked_foods = _blocked_food_terms(constraints_text)
    schedule_items, _ = _candidate_lines(schedule_text)
    nutrition_items, removed_food_items = _candidate_lines(
        nutrition_text,
        blocked_terms=blocked_foods,
    )
    exercise_items, _ = _candidate_lines(exercise_text)
    conflicts = _exercise_conflicts(schedule_text, exercise_text, constraints_text)
    if removed_food_items:
        conflicts.append(
            "One or more nutrition template items were excluded because they matched the sidecar constraint source."
        )

    sources = evidence_snapshot["sources"]
    lines = [
        f"# {profile_name}: Daily Lifestyle Draft",
        "",
        f"Report generated: {generated_at}",
        f"Profile: `{profile_slug}`",
        f"Target date: {target_date}",
        "",
        "## Source Status",
        "",
    ]
    for source_name in (
        "schedule_md_path",
        "nutrition_md_path",
        "exercise_md_path",
        "lifestyle_constraints_md_path",
    ):
        metadata = sources.get(source_name, {})
        path = metadata.get("path", "")
        path_suffix = f" - `{path}`" if path else ""
        lines.append(f"- `{source_name}`: {metadata.get('status', 'unknown')}{path_suffix}")

    lines.extend(
        [
            "",
            "## Constraint Authority",
            "",
            "- Sidecar constraints are read from `lifestyle_constraints_md_path` and are not copied into this draft.",
            "- Food triggers and symptom constraints override macro or weight targets.",
            "- Fixed schedule blocks override meal and workout placement unless the source marks them as flexible.",
            "",
            "## Schedule Draft",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in schedule_items[:8] or ["No schedule template lines available."])
    lines.extend(["", "## Nutrition Draft", ""])
    lines.extend(f"- {item}" for item in nutrition_items[:8] or ["No nutrition template lines available after applying constraints."])
    lines.extend(["", "## Exercise Draft", ""])
    lines.extend(f"- {item}" for item in exercise_items[:8] or ["No exercise template lines available."])
    lines.extend(["", "## Conflicts And Review Notes", ""])
    lines.extend(f"- {item}" for item in conflicts or ["No deterministic conflicts detected from the available Markdown sources."])

    return "\n".join(lines).rstrip() + "\n"
