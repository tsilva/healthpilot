"""Stable enums and field names used across the local workflow."""

ISSUE_STATUSES = {"active", "monitoring", "resolved", "parked"}
CONFIDENCE_FRAMES = {
    "clear conclusion",
    "likely diagnosis",
    "differential",
    "open question",
}

PRIORITY_BUCKETS = (
    "materially_narrows_differential",
    "changes_treatment_or_specialist_path",
    "resolves_missing_objective_evidence",
    "reduces_risk_if_delayed",
    "lower_value_optimization",
)

PRIORITY_CONTEXT_FIELDS = (
    "materially_narrows_differential",
    "changes_treatment_or_specialist_path",
    "resolves_missing_objective_evidence",
    "reduces_risk_if_delayed",
    "is_lower_value_optimization",
)

REQUIRED_ISSUE_FIELDS = (
    "profile_slug",
    "title",
    "status",
    "working_conclusion",
    "confidence_frame",
    "supporting_evidence",
    "contradicting_evidence",
    "next_best_action",
    "why_this_action_now",
    "specialist_type",
    "tests_or_discussions_to_request",
    "result_that_would_change_plan",
    "last_reviewed_at",
    "linked_sources",
)
