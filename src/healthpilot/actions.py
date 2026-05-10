"""Action ranking, state serialization, and plan report rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from healthpilot.constants import PRIORITY_BUCKETS
from healthpilot.lifestyle import LIFESTYLE_SOURCE_FIELDS


PRIORITY_LABELS = {
    "materially_narrows_differential": "Materially narrows the differential",
    "changes_treatment_or_specialist_path": "Could change treatment class or specialist path",
    "resolves_missing_objective_evidence": "Resolves missing objective evidence",
    "reduces_risk_if_delayed": "Reduces risk if delayed",
    "lower_value_optimization": "Lower-value optimization",
}

EXPECTED_PAYOFF = {
    "materially_narrows_differential": "High diagnostic clarification",
    "changes_treatment_or_specialist_path": "High downstream treatment impact",
    "resolves_missing_objective_evidence": "Closes a key evidence gap",
    "reduces_risk_if_delayed": "Reduces time-sensitive downside",
    "lower_value_optimization": "Optimization or monitoring value",
}


@dataclass(slots=True)
class RankedAction:
    issue_slug: str
    issue_title: str
    do_next: str
    why: str
    specialist_type: str
    what_to_ask_for: list[str]
    what_result_to_return_with: str
    priority_bucket: str
    expected_payoff: str
    related_issues: list[str]
    source_citations: list[str]

    def dedupe_key(self) -> str:
        return self.do_next.strip().lower()


def determine_priority_bucket(issue_payload: dict[str, Any]) -> str:
    context = issue_payload.get("priority_context", {}) or {}
    if context.get("materially_narrows_differential"):
        return PRIORITY_BUCKETS[0]
    if context.get("changes_treatment_or_specialist_path"):
        return PRIORITY_BUCKETS[1]
    if context.get("resolves_missing_objective_evidence"):
        return PRIORITY_BUCKETS[2]
    if context.get("reduces_risk_if_delayed"):
        return PRIORITY_BUCKETS[3]
    if context.get("is_lower_value_optimization"):
        return PRIORITY_BUCKETS[4]

    confidence = issue_payload["confidence_frame"]
    if confidence in {"differential", "open question"}:
        return PRIORITY_BUCKETS[0]
    if issue_payload["specialist_type"] and issue_payload["tests_or_discussions_to_request"]:
        return PRIORITY_BUCKETS[1]
    if issue_payload["result_that_would_change_plan"]:
        return PRIORITY_BUCKETS[2]
    return PRIORITY_BUCKETS[4]


def build_ranked_actions(issues: dict[str, dict[str, Any]]) -> list[RankedAction]:
    actions: list[RankedAction] = []
    for slug, issue in issues.items():
        if issue["status"] not in {"active", "monitoring"}:
            continue
        bucket = determine_priority_bucket(issue)
        actions.append(
            RankedAction(
                issue_slug=slug,
                issue_title=issue["title"],
                do_next=issue["next_best_action"],
                why=issue["why_this_action_now"],
                specialist_type=issue["specialist_type"],
                what_to_ask_for=issue["tests_or_discussions_to_request"],
                what_result_to_return_with=issue["result_that_would_change_plan"],
                priority_bucket=bucket,
                expected_payoff=EXPECTED_PAYOFF[bucket],
                related_issues=[slug],
                source_citations=list(issue.get("linked_sources", [])),
            )
        )

    actions.sort(
        key=lambda action: (
            PRIORITY_BUCKETS.index(action.priority_bucket),
            action.issue_title.lower(),
            action.do_next.lower(),
        )
    )
    return actions


def dedupe_actions(actions: list[RankedAction]) -> list[RankedAction]:
    deduped: list[RankedAction] = []
    seen: dict[str, RankedAction] = {}
    for action in actions:
        key = action.dedupe_key()
        if key not in seen:
            seen[key] = action
            deduped.append(action)
            continue
        existing = seen[key]
        if action.issue_slug not in existing.related_issues:
            existing.related_issues.append(action.issue_slug)
        for citation in action.source_citations:
            if citation not in existing.source_citations:
                existing.source_citations.append(citation)
    return deduped


def build_action_queue_payload(
    profile_slug: str,
    profile_name: str,
    generated_at: str,
    issues: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ranked = dedupe_actions(build_ranked_actions(issues))
    return {
        "profile_slug": profile_slug,
        "profile_name": profile_name,
        "generated_at": generated_at,
        "actions": [
            {
                "rank": index,
                "issue_slug": action.issue_slug,
                "issue_title": action.issue_title,
                "priority_bucket": action.priority_bucket,
                "priority_label": PRIORITY_LABELS[action.priority_bucket],
                "do_next": action.do_next,
                "why": action.why,
                "specialist_type": action.specialist_type,
                "what_to_ask_for": action.what_to_ask_for,
                "what_result_to_return_with": action.what_result_to_return_with,
                "expected_payoff": action.expected_payoff,
                "owner": "user",
                "related_issues": action.related_issues,
                "source_citations": action.source_citations,
            }
            for index, action in enumerate(ranked, start=1)
        ],
    }


def _describe_source_details(source_name: str, metadata: dict[str, Any]) -> list[str]:
    details = metadata.get("details", {}) or {}
    lines: list[str] = []

    if source_name == "labs_path":
        recent_results = details.get("recent_results", [])
        if recent_results:
            rendered = ", ".join(
                f"{item['date']} {item['label']} {item['value']}{item['unit']}"
                for item in recent_results[-3:]
            )
            lines.append(f"Recent results: {rendered}")
        abnormal_results = details.get("recent_abnormal_results", [])
        if abnormal_results:
            rendered = ", ".join(
                f"{item['date']} {item['label']} {item['value']}{item['unit']}"
                for item in abnormal_results[-3:]
            )
            lines.append(f"Recent flagged results: {rendered}")
    elif source_name == "health_log_path":
        headline = details.get("headline")
        if headline:
            lines.append(f"Health log headline: {headline}")
        processed_entries = details.get("recent_processed_entries", [])
        if processed_entries:
            lines.append(f"Recent processed entries: {', '.join(processed_entries)}")
    elif source_name == "exams_path":
        recent_files = details.get("recent_files", [])
        if recent_files:
            lines.append(f"Recent exam files: {', '.join(recent_files)}")
    elif source_name == "genetics_23andme_path":
        rsids = details.get("sample_rsids", [])
        if rsids:
            lines.append(f"Sample rsids: {', '.join(rsids)}")
    elif source_name in LIFESTYLE_SOURCE_FIELDS:
        headings = details.get("headings", [])
        if headings:
            lines.append(f"Markdown headings: {', '.join(headings[:6])}")
        snippets = details.get("relevant_snippets", [])
        if snippets:
            lines.append(f"Relevant snippets: {'; '.join(snippets[:4])}")

    latest_modified_at = metadata.get("latest_modified_at")
    if latest_modified_at:
        lines.append(f"Latest source update seen: {latest_modified_at}")

    return lines


def _current_active_condition_lines(issues: dict[str, dict[str, Any]]) -> list[str]:
    active_issues = [
        (slug, issue)
        for slug, issue in sorted(issues.items())
        if issue["status"] in {"active", "monitoring"}
    ]
    if not active_issues:
        return ["- No active or monitoring conditions are currently tracked in issue state."]

    lines = []
    for slug, issue in active_issues:
        lines.append(
            "- "
            f"{issue['title']} (`{slug}`): {issue['status']}; "
            f"{issue['confidence_frame']}; {issue['working_conclusion']}"
        )
    return lines


def _current_medication_stack_lines(evidence_packet: dict[str, Any] | None) -> list[str]:
    health_log = (evidence_packet or {}).get("health_log", {})
    current_stack = health_log.get("current_medication_supplement_stack", [])
    if current_stack:
        lines = [
            "- Current stack extracted from explicit health-log stack section; reconcile if newer entries changed it."
        ]
        for block in current_stack[:2]:
            location = block.get("path", "")
            line_number = block.get("line")
            heading = block.get("heading", "Current medication/supplement stack")
            if location and line_number:
                heading = f"{heading} ({location}:{line_number})"
            elif location:
                heading = f"{heading} ({location})"
            lines.append(f"- {heading}:")
            for item in block.get("items", [])[:12]:
                text = item.get("text", "Medication/supplement item captured.")
                item_line = item.get("line")
                item_location = item.get("path", location)
                suffix = (
                    f" ({item_location}:{item_line})"
                    if item_location and item_line
                    else ""
                )
                lines.append(f"- {text}{suffix}")
        return lines

    mentions = health_log.get("medication_supplement_mentions_needing_review", [])
    if not mentions:
        health_log_status = health_log.get("status")
        if health_log_status and health_log_status != "available":
            return [
                "- Current medication or supplement stack could not be extracted because "
                f"`health_log_path` is {health_log_status} in the live profile."
            ]
        return [
            "- No current medication or supplement stack was captured in the "
            "deterministic evidence packet; verify whether the health log has an explicit current-stack section."
        ]

    lines = [
        "- Complete current stack requires reconciliation; recent parsed medication/supplement evidence:"
    ]
    for mention in mentions[:8]:
        location = mention.get("path", "")
        line_number = mention.get("line")
        if location and line_number:
            location = f"{location}:{line_number}"
        text = mention.get("text", "Medication/supplement mention captured.")
        lines.append(f"- {text} ({location})" if location else f"- {text}")
    return lines


def render_plan_report(
    *,
    profile_slug: str,
    profile_name: str,
    generated_at: str,
    evidence_snapshot: dict[str, Any],
    evidence_packet: dict[str, Any] | None = None,
    issues: dict[str, dict[str, Any]],
    action_queue: dict[str, Any],
) -> str:
    source_status = evidence_snapshot["sources"]
    lines = [
        f"# {profile_name}: Action Plan",
        "",
        f"Report generated: {generated_at}",
        f"Profile: `{profile_slug}`",
        "",
        "## Current Status Summary",
        "",
        "### Current Active Conditions",
        "",
    ]
    lines.extend(_current_active_condition_lines(issues))
    lines.extend(
        [
            "",
            "### Current Medication / Supplement Stack",
            "",
        ]
    )
    lines.extend(_current_medication_stack_lines(evidence_packet))

    lines.extend(["", "## Source Status", ""])
    for source_name, metadata in source_status.items():
        sample = metadata.get("sample", [])
        sample_suffix = f" (sample: {', '.join(sample)})" if sample else ""
        path = metadata.get("path", "")
        path_suffix = f" - `{path}`" if path else ""
        lines.append(
            f"- `{source_name}`: {metadata.get('status', 'unknown')}{path_suffix}{sample_suffix}"
        )

    lines.extend(["", "## Current Evidence Snapshot", ""])
    for source_name, metadata in source_status.items():
        lines.append(f"### `{source_name}`")
        detail_lines = _describe_source_details(source_name, metadata)
        if detail_lines:
            lines.extend(f"- {item}" for item in detail_lines)
        else:
            lines.append("- No additional snapshot details captured.")
        lines.append("")

    lines.extend(
        [
            "",
            "## Top 3 Ranked Actions",
            "",
        ]
    )
    top_actions = action_queue.get("actions", [])[:3]
    if not top_actions:
        lines.append("- No active actions. All tracked issues are resolved or parked.")
    else:
        for action in top_actions:
            related = ", ".join(f"`{slug}`" for slug in action["related_issues"])
            lines.extend(
                [
                    f"### {action['rank']}. {action['do_next']}",
                    "",
                    f"- Priority: {action['priority_label']}",
                    f"- Expected payoff: {action['expected_payoff']}",
                    f"- Owner: {action['owner']}",
                    f"- Specialist type: {action['specialist_type']}",
                    f"- Related issues: {related}",
                    f"- Why now: {action['why']}",
                    f"- What to ask for: {', '.join(action['what_to_ask_for'])}",
                    f"- What to bring back: {action['what_result_to_return_with']}",
                    "",
                ]
            )

    lines.extend(["## Active Issues", ""])
    active_found = False
    for slug, issue in sorted(issues.items()):
        if issue["status"] not in {"active", "monitoring"}:
            continue
        active_found = True
        lines.extend(
            [
                f"### {issue['title']} (`{slug}`)",
                "",
                f"- Status: {issue['status']}",
                f"- Confidence frame: {issue['confidence_frame']}",
                f"- Working conclusion: {issue['working_conclusion']}",
                f"- Do next: {issue['next_best_action']}",
                f"- Why: {issue['why_this_action_now']}",
                f"- What to ask for: {', '.join(issue['tests_or_discussions_to_request'])}",
                f"- What result to return with: {issue['result_that_would_change_plan']}",
                "",
                "Supporting evidence:",
            ]
        )
        lines.extend(f"- {item}" for item in issue["supporting_evidence"])
        lines.extend(["", "Contradicting evidence:"])
        contradicting = issue["contradicting_evidence"] or ["None documented"]
        lines.extend(f"- {item}" for item in contradicting)
        lines.extend(["", "Linked sources:"])
        lines.extend(f"- {item}" for item in issue["linked_sources"])
        if issue.get("recent_updates"):
            lines.extend(["", "Recent updates:"])
            lines.extend(f"- {item}" for item in issue["recent_updates"])
        lines.append("")

    if not active_found:
        lines.append("No active or monitoring issues are currently tracked.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
