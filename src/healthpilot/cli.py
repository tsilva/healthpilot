"""CLI for deterministic Healthpilot evidence and state refreshes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from healthpilot.actions import build_action_queue_payload
from healthpilot.evidence import build_evidence_snapshot
from healthpilot.evidence_packet import (
    build_evidence_packet,
    evidence_packet_path,
    load_previous_evidence_packet,
)
from healthpilot.issues import (
    ValidationError,
    load_issue_collection,
    load_issue_store,
    save_issue_store,
)
from healthpilot.jsonio import write_json
from healthpilot.lifestyle import render_daily_plan
from healthpilot.output_migration import migrate_output_layout
from healthpilot.paths import (
    ensure_repo_dirs,
    profiles_state_path,
    report_output_path,
    state_path,
)
from healthpilot.profile import ProfileContext, load_profile_context
from healthpilot.selfdecode import (
    fetch_selfdecode_genotypes,
    genotype_cache_path,
    load_genotype_cache,
    normalize_rsids,
    profile_selfdecode_config,
    resolve_selfdecode_token,
    update_genotype_cache,
)
from healthpilot.report_validation import REPORT_CONTRACTS, validate_report
from healthpilot.google_health import METRICS, retrieve
from healthpilot.google_health_auth import GoogleHealthError, configure, connect, connection_status


def _profile_with_wearables(args: argparse.Namespace) -> ProfileContext:
    profile = load_profile_context(args.profile, home_dir=args.home_dir)
    metrics = getattr(args, "wearable_metrics", None)
    start, end = getattr(args, "wearable_start", None), getattr(args, "wearable_end", None)
    if metrics or start or end or getattr(args, "wearable_refresh", False):
        if not (metrics and start and end):
            raise ValidationError("Wearable retrieval requires --wearable-metrics, --wearable-start and --wearable-end.")
        profile.wearable_evidence = retrieve(profile=profile, home_dir=args.home_dir,
            start=start, end=end, metrics=metrics, refresh=args.wearable_refresh)
    return profile


def _calendar_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("Use a calendar date in YYYY-MM-DD format.") from None


def _add_wearable_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--wearable-metrics", nargs="+", choices=tuple(METRICS))
    parser.add_argument("--wearable-start", type=_calendar_date, help="Inclusive source civil date.")
    parser.add_argument("--wearable-end", type=_calendar_date, help="Inclusive source civil date.")
    parser.add_argument("--wearable-refresh", action="store_true", help="Also refresh requested historical wearable dates.")


def run_google_health_configure(args: argparse.Namespace) -> int:
    configure(args.home_dir, args.client_file)
    print("Shared Google OAuth application configured.")
    return 0


def run_google_health_connect(args: argparse.Namespace) -> int:
    profile = load_profile_context(args.profile, home_dir=args.home_dir)
    print(json.dumps(connect(profile, args.home_dir, args.account, args.timezone), indent=2))
    return 0


def run_google_health_status(args: argparse.Namespace) -> int:
    profile = load_profile_context(args.profile, home_dir=args.home_dir)
    print(json.dumps(connection_status(profile, args.home_dir), indent=2))
    return 0


def run_google_health(args: argparse.Namespace) -> int:
    profile = load_profile_context(args.profile, home_dir=args.home_dir)
    result = retrieve(profile=profile, home_dir=args.home_dir,
                      start=args.start, end=args.end,
                      metrics=args.metrics, refresh=args.refresh)
    print(json.dumps(result, indent=2))
    return 0


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_legacy_issue_dir(repo_root: Path, *, profile_slug: str) -> dict[str, dict[str, Any]]:
    legacy_dir = state_path(repo_root, "issues")
    if not legacy_dir.exists():
        return {}

    issues: dict[str, dict[str, Any]] = {}
    for issue_file in load_issue_collection(legacy_dir):
        if issue_file.payload["profile_slug"] != profile_slug:
            continue
        issues[issue_file.slug] = issue_file.payload
    return issues


def _load_profile_issues(repo_root: Path, *, profile_slug: str) -> dict[str, dict[str, Any]]:
    issues_path = profiles_state_path(repo_root, profile_slug, "issues.json")
    issues = load_issue_store(issues_path)
    if issues:
        return issues
    return _read_legacy_issue_dir(repo_root, profile_slug=profile_slug)


def _write_profile_state(
    *,
    repo_root: Path,
    profile_context: Any,
    generated_at: str,
    evidence_snapshot: dict[str, Any],
    issues: dict[str, dict[str, Any]],
) -> Path:
    actions_payload = build_action_queue_payload(
        profile_slug=profile_context.slug,
        profile_name=profile_context.cache_payload["profile_name"],
        generated_at=generated_at,
        issues=issues,
    )
    profile_state_dir = profiles_state_path(repo_root, profile_context.slug)
    sources_path = profile_state_dir / "sources.json"
    issues_path = profile_state_dir / "issues.json"
    actions_path = profile_state_dir / "actions.json"

    write_json(sources_path, evidence_snapshot)
    save_issue_store(
        issues_path,
        profile_slug=profile_context.slug,
        profile_name=profile_context.cache_payload["profile_name"],
        generated_at=generated_at,
        issues=issues,
    )
    write_json(actions_path, actions_payload)
    return actions_path


def _sync_issue_inputs(
    repo_root: Path,
    source_path: Path,
    *,
    profile_slug: str,
    profile_name: str,
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    issues = _load_profile_issues(repo_root, profile_slug=profile_slug)
    for issue_file in load_issue_collection(source_path):
        if issue_file.payload["profile_slug"] != profile_slug:
            continue
        payload = dict(issue_file.payload)
        payload["profile_slug"] = profile_slug
        issues[issue_file.slug] = payload

    save_issue_store(
        profiles_state_path(repo_root, profile_slug, "issues.json"),
        profile_slug=profile_slug,
        profile_name=profile_name,
        generated_at=generated_at,
        issues=issues,
    )
    return issues


def _build_and_write_evidence_packet(
    *,
    repo_root: Path,
    profile_context: Any,
    generated_at: str,
    issues: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    previous_packet = load_previous_evidence_packet(repo_root, profile_context.slug)
    packet = build_evidence_packet(
        repo_root=repo_root,
        profile_context=profile_context,
        generated_at=generated_at,
        issues=issues,
        previous_packet=previous_packet,
    )
    write_json(evidence_packet_path(repo_root, profile_context.slug), packet)
    return packet


def run_evidence_packet(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    profile_context = _profile_with_wearables(args)
    ensure_repo_dirs(repo_root, profile_context.slug)
    generated_at = _utc_now()
    issues = _load_profile_issues(repo_root, profile_slug=profile_context.slug)
    _build_and_write_evidence_packet(
        repo_root=repo_root,
        profile_context=profile_context,
        generated_at=generated_at,
        issues=issues,
    )
    return 0


def run_plan(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    profile_context = _profile_with_wearables(args)
    ensure_repo_dirs(repo_root, profile_context.slug)
    generated_at = _utc_now()

    issues = _load_profile_issues(repo_root, profile_slug=profile_context.slug)
    if args.issues_from:
        issues = _sync_issue_inputs(
            repo_root,
            args.issues_from.resolve(),
            profile_slug=profile_context.slug,
            profile_name=profile_context.cache_payload["profile_name"],
            generated_at=generated_at,
        )
    evidence_packet = _build_and_write_evidence_packet(
        repo_root=repo_root,
        profile_context=profile_context,
        generated_at=generated_at,
        issues=issues,
    )
    evidence_snapshot = evidence_packet["source_snapshot"]
    _write_profile_state(
        repo_root=repo_root,
        profile_context=profile_context,
        generated_at=generated_at,
        evidence_snapshot=evidence_snapshot,
        issues=issues,
    )
    return 0


def _validate_plan_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError("--date must use YYYY-MM-DD format.") from exc
    return value


def run_daily_plan(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    profile_context = _profile_with_wearables(args)
    ensure_repo_dirs(repo_root, profile_context.slug)
    generated_at = _utc_now()
    target_date = _validate_plan_date(args.date or generated_at[:10])
    evidence_snapshot = build_evidence_snapshot(profile_context, generated_at=generated_at)

    write_json(
        profiles_state_path(repo_root, profile_context.slug, "sources.json"),
        evidence_snapshot,
    )
    report_body = render_daily_plan(
        profile_slug=profile_context.slug,
        profile_name=profile_context.cache_payload["profile_name"],
        generated_at=generated_at,
        target_date=target_date,
        evidence_snapshot=evidence_snapshot,
    )
    report_name = f"{target_date}-{profile_context.slug}-daily-plan.md"
    report_path = report_output_path(
        repo_root,
        profile_context.slug,
        "daily-plan",
        report_name,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_body, encoding="utf-8")
    return 0


def run_validate_report(args: argparse.Namespace) -> int:
    report_path = args.report.resolve()
    previous_path = args.previous.resolve() if args.previous else None
    errors = validate_report(
        report_path.read_text(encoding="utf-8"),
        report_type=args.report_type,
        report_path=report_path,
        previous_path=previous_path,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("report validation passed")
    return 0


def run_migrate_output_layout(args: argparse.Namespace) -> int:
    manifest = migrate_output_layout(args.repo_root.resolve(), apply=args.apply)
    counts = Counter(item["operation"] for item in manifest["operations"])
    mode = "applied" if args.apply else "dry run"
    print(
        f"output migration {mode}: "
        f"{counts.get('move', 0)} moves, "
        f"{counts.get('conflict', 0)} conflicts, "
        f"{counts.get('deduplicate', 0)} duplicates, "
        f"{len(manifest['os_metadata'])} metadata files"
    )
    print(f"manifest\t{manifest['manifest_path']}")
    return 0


def run_selfdecode_genotypes(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    profile_context = _profile_with_wearables(args)
    ensure_repo_dirs(repo_root, profile_context.slug)

    rsids = normalize_rsids(args.rsids)
    if not rsids:
        raise ValidationError("Provide at least one rsID with --rsids.")

    cache_path = genotype_cache_path(repo_root, profile_context.slug)
    cache = load_genotype_cache(cache_path)
    cached_items = cache.get("items", {})
    missing = [
        rsid
        for rsid in rsids
        if args.refresh or rsid not in cached_items
    ]

    if missing:
        token = resolve_selfdecode_token(profile_context, args.jwt_token)
        if not token:
            raise ValidationError(
                "SelfDecode JWT token is required for uncached rsIDs: "
                f"{', '.join(missing)}. Pass --jwt-token or set SELFDECODE_JWT."
            )
        selfdecode = profile_selfdecode_config(profile_context)
        profile_id = selfdecode.get("profile_id", "")
        try:
            fetched = fetch_selfdecode_genotypes(
                profile_id=profile_id,
                rsids=missing,
                jwt_token=token,
            )
        except (RuntimeError, ValueError) as exc:
            raise ValidationError(str(exc)) from exc
        update_genotype_cache(
            repo_root=repo_root,
            profile_context=profile_context,
            fetched_items=fetched,
        )
        cache = load_genotype_cache(cache_path)
        cached_items = cache.get("items", {})

    print("rsid\tgenotype\tstatus\tvariant_ids\tcached_at")
    for rsid in rsids:
        item = cached_items.get(rsid, {})
        print(
            "\t".join(
                [
                    rsid,
                    item.get("genotype", "NO_RESULT"),
                    item.get("status", "missing"),
                    ",".join(item.get("variant_ids", [])),
                    item.get("fetched_at", ""),
                ]
            )
        )
    print(f"cache\t{cache_path}")
    return 0


def _run_deprecated_alias(args: argparse.Namespace, alias: str) -> int:
    message = (
        f"warning: `healthpilot {alias}` is deprecated; use "
        f"`healthpilot plan --profile {args.profile}`.\n"
    )
    print(message, end="")
    return run_plan(args)


def run_intake(args: argparse.Namespace) -> int:
    return _run_deprecated_alias(args, "intake")


def run_review(args: argparse.Namespace) -> int:
    return _run_deprecated_alias(args, "review")


def run_outcome_update(args: argparse.Namespace) -> int:
    if args.update_file or args.revised_issue:
        print(
            "warning: manual outcome update files are deprecated; rescan the parsed sources and rerun `healthpilot plan`.\n",
            end="",
        )
    return _run_deprecated_alias(args, "outcome-update")


def _add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", required=True, help="Profile name or absolute YAML path.")


def _add_optional_issues_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--issues-from",
        type=Path,
        help="Deprecated compatibility input for issue JSON drafts; imported into the per-profile issue store before planning.",
    )


def _add_deprecated_outcome_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--update-file",
        type=Path,
        help="Deprecated compatibility argument. Parsed source folders are now the canonical input.",
    )
    parser.add_argument(
        "--revised-issue",
        type=Path,
        help="Deprecated compatibility argument. Parsed source folders are now the canonical input.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="healthpilot",
        description="Refresh deterministic evidence and state for agent-facing Healthpilot workflows.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root where .state/ and .output/ live.",
    )
    parser.add_argument(
        "--home-dir",
        type=Path,
        default=Path.home(),
        help="Home directory used to resolve ~/.config/healthpilot profiles.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    application = subparsers.add_parser("google-health-configure", help="Import a shared Desktop OAuth app.")
    application.add_argument("--client-file", type=Path, required=True)
    application.set_defaults(func=run_google_health_configure)
    connection = subparsers.add_parser("google-health-connect", help="Authorize one profile's Google account.")
    _add_profile_argument(connection)
    connection.add_argument("--account", required=True, help="Expected verified Google email.")
    connection.add_argument("--timezone", default="UTC", help="IANA timezone for the seven-day refresh clock.")
    connection.set_defaults(func=run_google_health_connect)
    status = subparsers.add_parser("google-health-status", help="Show the selected profile's account and scopes.")
    _add_profile_argument(status)
    status.set_defaults(func=run_google_health_status)

    wearable = subparsers.add_parser("google-health", help="Retrieve profile-scoped wearable evidence.")
    _add_profile_argument(wearable)
    wearable.add_argument("--metrics", nargs="+", required=True, choices=tuple(METRICS))
    wearable.add_argument("--start", required=True, type=_calendar_date, help="Inclusive civil date, YYYY-MM-DD.")
    wearable.add_argument("--end", required=True, type=_calendar_date, help="Inclusive civil date, YYYY-MM-DD.")
    wearable.add_argument("--refresh", action="store_true")
    wearable.set_defaults(func=run_google_health)

    plan_description = (
        "Rescan parsed source folders and refresh per-profile evidence, issue, and action state."
    )
    plan = subparsers.add_parser(
        "plan",
        help=plan_description,
        description=plan_description,
    )
    _add_profile_argument(plan)
    _add_wearable_arguments(plan)
    _add_optional_issues_argument(plan)
    plan.set_defaults(func=run_plan)

    packet = subparsers.add_parser(
        "evidence-packet",
        help="Build the deterministic evidence packet used by agent-facing planning.",
    )
    _add_profile_argument(packet)
    _add_wearable_arguments(packet)
    packet.set_defaults(func=run_evidence_packet)

    daily_plan = subparsers.add_parser(
        "daily-plan",
        help="Render a draft daily lifestyle plan from profile-linked Markdown sources.",
    )
    _add_profile_argument(daily_plan)
    _add_wearable_arguments(daily_plan)
    daily_plan.add_argument(
        "--date",
        help="Target date for the draft plan in YYYY-MM-DD format. Defaults to today.",
    )
    daily_plan.set_defaults(func=run_daily_plan)

    validate = subparsers.add_parser(
        "validate-report",
        help="Validate a user-facing Markdown report against the shared contract.",
    )
    validate.add_argument(
        "--type",
        dest="report_type",
        required=True,
        choices=tuple(REPORT_CONTRACTS),
        help="Report contract to validate.",
    )
    validate.add_argument("--report", type=Path, required=True, help="Markdown report path.")
    validate.add_argument(
        "--previous",
        type=Path,
        help="Previous comparable report for repeat-report change validation.",
    )
    validate.set_defaults(func=run_validate_report)

    migrate = subparsers.add_parser(
        "migrate-output-layout",
        help="Plan or apply migration to profile/report output buckets.",
    )
    migrate.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration. Without this flag, only a manifest is generated.",
    )
    migrate.set_defaults(func=run_migrate_output_layout)

    selfdecode = subparsers.add_parser(
        "selfdecode-genotypes",
        help="Fetch SelfDecode genotypes by rsID and cache them under .state/.",
    )
    _add_profile_argument(selfdecode)
    selfdecode.add_argument(
        "--rsids",
        nargs="+",
        required=True,
        help="One or more rsIDs. Comma-separated values are also accepted.",
    )
    selfdecode.add_argument(
        "--jwt-token",
        help="SelfDecode service JWT. If omitted, SELFDECODE_JWT is used.",
    )
    selfdecode.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh requested rsIDs from SelfDecode even if cached.",
    )
    selfdecode.set_defaults(func=run_selfdecode_genotypes)

    intake = subparsers.add_parser(
        "intake",
        help="Deprecated alias for `plan`.",
    )
    _add_profile_argument(intake)
    _add_optional_issues_argument(intake)
    intake.set_defaults(func=run_intake)

    review = subparsers.add_parser(
        "review",
        help="Deprecated alias for `plan`.",
    )
    _add_profile_argument(review)
    _add_optional_issues_argument(review)
    review.set_defaults(func=run_review)

    outcome = subparsers.add_parser(
        "outcome-update",
        help="Deprecated alias for `plan`. Parsed source folders are now the canonical input.",
    )
    _add_profile_argument(outcome)
    _add_optional_issues_argument(outcome)
    _add_deprecated_outcome_arguments(outcome)
    outcome.set_defaults(func=run_outcome_update)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValidationError, GoogleHealthError) as exc:
        parser.exit(status=2, message=f"error: {exc}\n")
