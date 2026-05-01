from __future__ import annotations

import json
from pathlib import Path

from healthpilot.cli import main


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_profile(
    home_dir: Path,
    *,
    slug: str = "test-user",
    display_name: str = "Test User",
    missing_exams: bool = False,
    lifestyle_sources: bool = False,
    missing_lifestyle_source: str | None = None,
    unreadable_lifestyle_source: str | None = None,
    selfdecode: bool = False,
) -> dict[str, Path]:
    config_dir = home_dir / ".config" / "healthpilot" / "profiles"
    config_dir.mkdir(parents=True, exist_ok=True)

    profile_root = home_dir / "data" / slug

    labs_dir = profile_root / "labs"
    labs_dir.mkdir(parents=True, exist_ok=True)
    (labs_dir / "all.csv").write_text(
        "\n".join(
            [
                "date,lab_name,value,lab_unit,is_above_limit,is_below_limit,review_needed",
                "2026-04-10,Ferritin,18,ng/mL,false,true,false",
                "2026-04-12,Hemoglobin,11.6,g/dL,false,true,true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    health_log_dir = profile_root / "health-log"
    entries_dir = health_log_dir / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)
    (health_log_dir / "health_log.md").write_text(
        "# Health log overview\nRecent fatigue and follow-up labs.\n",
        encoding="utf-8",
    )
    (entries_dir / "2026-04-12.processed.md").write_text(
        "Processed summary for 2026-04-12.\n",
        encoding="utf-8",
    )

    genetics_file = profile_root / "23andme.txt"
    genetics_file.parent.mkdir(parents=True, exist_ok=True)
    genetics_file.write_text(
        "# raw 23andme export\nrs123\t1\t12345\tAA\nrs456\t2\t54321\tGG\n",
        encoding="utf-8",
    )

    exams_dir = profile_root / "exams"
    if not missing_exams:
        exams_dir.mkdir(parents=True, exist_ok=True)
        (exams_dir / "summary.md").write_text("# exam summary\n", encoding="utf-8")

    lifestyle_paths: dict[str, Path] = {}
    if lifestyle_sources or missing_lifestyle_source or unreadable_lifestyle_source:
        lifestyle_dir = profile_root / "lifestyle"
        lifestyle_dir.mkdir(parents=True, exist_ok=True)
        lifestyle_content = {
            "schedule_md_path": (
                "# Daily Schedule\n"
                "## Default Day\n"
                "- Fixed work 09:00-17:00\n"
                "- Sleep 23:00-07:00\n"
            ),
            "nutrition_md_path": (
                "# Nutrition Plan\n"
                "## Default Meal Plan\n"
                "- Breakfast: banana and oats\n"
                "- Lunch: rice and chicken\n"
            ),
            "exercise_md_path": (
                "# Exercise Plan\n"
                "## Default Training Plan\n"
                "- Gym workout 10:00-11:00\n"
            ),
            "lifestyle_constraints_md_path": (
                "# Lifestyle Constraints\n"
                "## Global Precedence\n"
                "1. Symptom triggers and medical constraints\n"
                "## Nutrition Constraints\n"
                "- Foods to avoid: banana\n"
                "## Regeneration Rules\n"
                "- What may be changed: generated drafts only\n"
            ),
        }
        filenames = {
            "schedule_md_path": "daily-schedule.md",
            "nutrition_md_path": "nutrition-plan.md",
            "exercise_md_path": "exercise-plan.md",
            "lifestyle_constraints_md_path": "lifestyle-constraints.md",
        }
        for field, content in lifestyle_content.items():
            path = lifestyle_dir / filenames[field]
            lifestyle_paths[field] = path
            if field == missing_lifestyle_source:
                continue
            path.write_text(content, encoding="utf-8")
            if field == unreadable_lifestyle_source:
                path.chmod(0)

    lifestyle_profile_fields = ""
    for field, path in lifestyle_paths.items():
        lifestyle_profile_fields += f'  {field}: "{path}"\n'
    selfdecode_profile_fields = ""
    if selfdecode:
        selfdecode_profile_fields = """
  selfdecode:
    enabled: true
    profile_id: "profile-123"
"""

    profile = f"""
name: "{display_name}"
demographics:
  date_of_birth: "1990-01-15"
  gender: "female"

data_sources:
  labs_path: "{labs_dir}"
  exams_path: "{exams_dir}"
  health_log_path: "{health_log_dir}"
  genetics_23andme_path: "{genetics_file}"
{lifestyle_profile_fields.rstrip()}
{selfdecode_profile_fields.rstrip()}
"""
    (config_dir / f"{slug}.yaml").write_text(profile.strip() + "\n", encoding="utf-8")
    return {
        "labs_dir": labs_dir,
        "exams_dir": exams_dir,
        "health_log_dir": health_log_dir,
        "entries_dir": entries_dir,
        "genetics_file": genetics_file,
        **lifestyle_paths,
    }


class _FakeHTTPResponse:
    def __init__(self, payload: list[dict]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _issue_payload(
    *,
    profile_slug: str = "test-user",
    title: str,
    confidence_frame: str,
    next_best_action: str,
    why: str,
    status: str = "active",
    priority_context: dict | None = None,
) -> dict:
    return {
        "profile_slug": profile_slug,
        "title": title,
        "status": status,
        "working_conclusion": "Working conclusion for test coverage.",
        "confidence_frame": confidence_frame,
        "supporting_evidence": ["Supporting evidence"],
        "contradicting_evidence": ["Contradicting evidence"],
        "next_best_action": next_best_action,
        "why_this_action_now": why,
        "specialist_type": "hematology",
        "tests_or_discussions_to_request": ["Discuss a targeted next test"],
        "result_that_would_change_plan": "Return with the new result so the plan can be updated.",
        "last_reviewed_at": "2026-04-15T00:00:00Z",
        "linked_sources": ["/tmp/source.md"],
        "priority_context": priority_context
        or {
            "materially_narrows_differential": False,
            "changes_treatment_or_specialist_path": False,
            "resolves_missing_objective_evidence": False,
            "reduces_risk_if_delayed": False,
            "is_lower_value_optimization": False,
        },
        "recent_updates": [],
    }


def _write_issue_store(
    repo_root: Path,
    *,
    profile_slug: str,
    profile_name: str = "Test User",
    issues: dict[str, dict],
) -> None:
    _write_json(
        repo_root / ".state" / "profiles" / profile_slug / "issues.json",
        {
            "profile_slug": profile_slug,
            "profile_name": profile_name,
            "generated_at": "2026-04-15T00:00:00Z",
            "issues": [{"slug": slug, **payload} for slug, payload in issues.items()],
        },
    )


def _external_source_snapshot(paths: dict[str, Path]) -> dict[str, str]:
    root_paths = [
        paths["labs_dir"],
        paths["exams_dir"],
        paths["health_log_dir"],
        paths["genetics_file"],
    ]
    for field in (
        "schedule_md_path",
        "nutrition_md_path",
        "exercise_md_path",
        "lifestyle_constraints_md_path",
    ):
        if field in paths:
            root_paths.append(paths[field])

    snapshot: dict[str, str] = {}
    for root_path in root_paths:
        if root_path.is_file():
            candidates = [root_path]
        elif root_path.exists():
            candidates = [path for path in root_path.rglob("*") if path.is_file()]
        else:
            candidates = []
        for path in candidates:
            snapshot[str(path)] = path.read_text(encoding="utf-8")
    return snapshot


def test_plan_creates_per_profile_state_and_report_on_first_run(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir)

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    profile_state_dir = repo_root / ".state" / "profiles" / "test-user"
    assert (profile_state_dir / "sources.json").exists()
    assert (profile_state_dir / "issues.json").exists()
    assert (profile_state_dir / "actions.json").exists()
    assert (profile_state_dir / "evidence-packet.json").exists()

    sources = json.loads((profile_state_dir / "sources.json").read_text())
    packet = json.loads((profile_state_dir / "evidence-packet.json").read_text())
    assert sources == packet["source_snapshot"]
    assert (
        sources["sources"]["health_log_path"]["details"]["recent_processed_entries"]
        == ["2026-04-12.processed.md"]
    )
    actions = json.loads((profile_state_dir / "actions.json").read_text())
    assert actions["actions"] == []

    report = next((repo_root / ".output" / "test-user").glob("????-??-??-test-user-action-plan.md"))
    report_text = report.read_text(encoding="utf-8")
    assert "Current Evidence Snapshot" in report_text
    assert "No active actions. All tracked issues are resolved or parked." in report_text


def test_plan_uses_profile_issue_store_and_dedupes_actions(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir)

    shared_action = "Book a targeted hematology visit."
    _write_issue_store(
        repo_root,
        profile_slug="test-user",
        issues={
            "issue-a": _issue_payload(
                title="Issue A",
                confidence_frame="differential",
                next_best_action=shared_action,
                why="This materially narrows the differential.",
            ),
            "issue-b": _issue_payload(
                title="Issue B",
                confidence_frame="open question",
                next_best_action=shared_action,
                why="This is still the best next step.",
            ),
        },
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    actions = json.loads((repo_root / ".state" / "profiles" / "test-user" / "actions.json").read_text())
    assert len(actions["actions"]) == 1
    assert sorted(actions["actions"][0]["related_issues"]) == ["issue-a", "issue-b"]
    assert actions["actions"][0]["source_citations"] == ["/tmp/source.md"]


def test_evidence_packet_creates_factual_packet_from_all_sources(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    paths = _write_profile(home_dir, lifestyle_sources=True)
    (paths["labs_dir"] / "all.csv").write_text(
        "\n".join(
            [
                "date,lab_name,value,lab_unit,is_above_limit,is_below_limit,review_needed,source_file,page_number",
                "2026-04-10,Ferritin,18,ng/mL,false,true,false,lab-a.pdf,1",
                "2026-04-12,Hemoglobin,11.6,g/dL,false,true,true,lab-b.pdf,2",
                "2026-04-15,Ferritin,22,ng/mL,false,false,false,lab-c.pdf,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (paths["entries_dir"] / "2026-04-15.processed.md").write_text(
        "Fatigue improved after sleep stabilized.\n"
        "Started magnesium supplement at night and stopped pantoprazole.\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "evidence-packet",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    packet_path = repo_root / ".state" / "profiles" / "test-user" / "evidence-packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["profile_slug"] == "test-user"
    assert packet["source_freshness"]["labs_path"]["status"] == "available"
    assert packet["source_freshness"]["exams_path"]["status"] == "available"
    assert packet["source_freshness"]["health_log_path"]["status"] == "available"
    assert packet["genetics"]["sample_rsids"] == ["rs123", "rs456"]
    assert packet["lifestyle"]["lifestyle_constraints_md_path"]["status"] == "available"
    assert "2026-04-15" in packet["labs"]["latest_lab_dates"]
    assert any(item["label"] == "Hemoglobin" for item in packet["labs"]["abnormal_markers"])
    assert {"label": "Ferritin", "date_count": 2} in packet["labs"]["trend_candidates"]
    assert packet["exams"]["latest_exam_summaries"][0]["path"].endswith("summary.md")
    assert any(
        "Fatigue improved" in item["text"]
        for item in packet["health_log"]["unresolved_symptom_or_treatment_signal_lines"]
    )
    assert any(
        "magnesium supplement" in item["text"]
        for item in packet["health_log"]["medication_supplement_mentions_needing_review"]
    )


def test_selfdecode_genotypes_uses_cache_without_token(tmp_path: Path, capsys) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir, selfdecode=True)
    cache_path = repo_root / ".state" / "profiles" / "test-user" / "selfdecode-genotypes.json"
    _write_json(
        cache_path,
        {
            "profile_slug": "test-user",
            "profile_name": "Test User",
            "source": "selfdecode",
            "updated_at": "2026-04-15T00:00:00Z",
            "items": {
                "rs123": {
                    "rsid": "rs123",
                    "status": "available",
                    "genotype": "AA",
                    "genotypes": ["A", "A"],
                    "variant_ids": ["ref", "ref"],
                    "profile_id": "profile-123",
                    "source": "selfdecode",
                    "fetched_at": "2026-04-15T00:00:00Z",
                }
            },
        },
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "selfdecode-genotypes",
            "--profile",
            "test-user",
            "--rsids",
            "rs123",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "rs123\tAA\tavailable\tref,ref\t2026-04-15T00:00:00Z" in out


def test_selfdecode_genotypes_fetches_and_caches_missing_rsids(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir, selfdecode=True)

    def fake_urlopen(request, timeout):
        assert timeout == 30
        assert request.headers["Authorization"] == "JWT token-123"
        assert "profile_id=profile-123" in request.full_url
        assert "rsid=rs456" in request.full_url
        return _FakeHTTPResponse(
            [
                {
                    "profile_id": "profile-123",
                    "rsid": "rs456",
                    "genotypes": ["G", "G"],
                    "variant_ids": ["ref", "ref"],
                }
            ]
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("SELFDECODE_JWT", "JWT token-123")

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "selfdecode-genotypes",
            "--profile",
            "test-user",
            "--rsids",
            "rs456",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "rs456\tGG\tavailable\tref,ref\t" in out
    cache = json.loads(
        (repo_root / ".state" / "profiles" / "test-user" / "selfdecode-genotypes.json").read_text(
            encoding="utf-8"
        )
    )
    assert cache["items"]["rs456"]["genotype"] == "GG"
    assert "token-123" not in json.dumps(cache)


def test_evidence_packet_detects_changed_files_since_last_run(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    paths = _write_profile(home_dir)

    first_exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "evidence-packet",
            "--profile",
            "test-user",
        ]
    )
    assert first_exit_code == 0

    (paths["entries_dir"] / "2026-04-16.processed.md").write_text(
        "Sleep worse after a medication change.\n",
        encoding="utf-8",
    )

    second_exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "evidence-packet",
            "--profile",
            "test-user",
        ]
    )
    assert second_exit_code == 0

    packet = json.loads(
        (repo_root / ".state" / "profiles" / "test-user" / "evidence-packet.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        item["change_type"] == "added"
        and item["source_name"] == "health_log_path"
        and item["relative_path"] == "entries/2026-04-16.processed.md"
        for item in packet["changed_files_since_last_run"]
    )


def test_evidence_packet_reports_missing_and_unreadable_sources(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    paths = _write_profile(
        home_dir,
        missing_exams=True,
        lifestyle_sources=True,
        unreadable_lifestyle_source="exercise_md_path",
    )

    try:
        exit_code = main(
            [
                "--repo-root",
                str(repo_root),
                "--home-dir",
                str(home_dir),
                "evidence-packet",
                "--profile",
                "test-user",
            ]
        )

        assert exit_code == 0
        packet = json.loads(
            (repo_root / ".state" / "profiles" / "test-user" / "evidence-packet.json").read_text(
                encoding="utf-8"
            )
        )
        assert packet["source_freshness"]["exams_path"]["status"] == "missing"
        assert packet["source_freshness"]["exercise_md_path"]["status"] == "unreadable"
        assert packet["exams"]["status"] == "missing"
        assert packet["lifestyle"]["exercise_md_path"]["status"] == "unreadable"
    finally:
        paths["exercise_md_path"].chmod(0o644)


def test_evidence_packet_does_not_write_external_sources(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    paths = _write_profile(home_dir, lifestyle_sources=True)
    before = _external_source_snapshot(paths)

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "evidence-packet",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    assert _external_source_snapshot(paths) == before


def test_plan_reports_missing_sources(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir, missing_exams=True)

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    report = next((repo_root / ".output" / "test-user").glob("????-??-??-test-user-action-plan.md"))
    report_text = report.read_text(encoding="utf-8")
    assert "`exams_path`: missing" in report_text


def test_plan_rescans_updated_sources(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    paths = _write_profile(home_dir)

    first_exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "test-user",
        ]
    )
    assert first_exit_code == 0

    (paths["entries_dir"] / "2026-04-15.processed.md").write_text(
        "Processed summary for 2026-04-15.\n",
        encoding="utf-8",
    )
    (paths["labs_dir"] / "all.csv").write_text(
        "\n".join(
            [
                "date,lab_name,value,lab_unit,is_above_limit,is_below_limit,review_needed",
                "2026-04-10,Ferritin,18,ng/mL,false,true,false",
                "2026-04-12,Hemoglobin,11.6,g/dL,false,true,true",
                "2026-04-15,CRP,9.1,mg/L,true,false,true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    second_exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "test-user",
        ]
    )
    assert second_exit_code == 0

    sources = json.loads((repo_root / ".state" / "profiles" / "test-user" / "sources.json").read_text())
    assert "2026-04-15.processed.md" in sources["sources"]["health_log_path"]["details"]["recent_processed_entries"]
    flagged = sources["sources"]["labs_path"]["details"]["recent_abnormal_results"]
    assert any(item["label"] == "CRP" for item in flagged)


def test_plan_captures_lifestyle_markdown_sources(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir, lifestyle_sources=True)

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    sources = json.loads((repo_root / ".state" / "profiles" / "test-user" / "sources.json").read_text())
    assert sources["sources"]["schedule_md_path"]["status"] == "available"
    assert "Default Day" in sources["sources"]["schedule_md_path"]["details"]["headings"]
    constraint_snippets = sources["sources"]["lifestyle_constraints_md_path"]["details"]["relevant_snippets"]
    assert any("Foods to avoid" in snippet for snippet in constraint_snippets)

    report = next((repo_root / ".output" / "test-user").glob("????-??-??-test-user-action-plan.md"))
    report_text = report.read_text(encoding="utf-8")
    assert "`lifestyle_constraints_md_path`: available" in report_text
    assert "Markdown headings" in report_text


def test_plan_reports_lifestyle_markdown_source_statuses(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    paths = _write_profile(
        home_dir,
        lifestyle_sources=True,
        missing_lifestyle_source="nutrition_md_path",
        unreadable_lifestyle_source="exercise_md_path",
    )

    try:
        exit_code = main(
            [
                "--repo-root",
                str(repo_root),
                "--home-dir",
                str(home_dir),
                "plan",
                "--profile",
                "test-user",
            ]
        )

        assert exit_code == 0
        sources = json.loads((repo_root / ".state" / "profiles" / "test-user" / "sources.json").read_text())
        assert sources["sources"]["schedule_md_path"]["status"] == "available"
        assert sources["sources"]["nutrition_md_path"]["status"] == "missing"
        assert sources["sources"]["exercise_md_path"]["status"] == "unreadable"
        assert sources["sources"]["lifestyle_constraints_md_path"]["status"] == "available"
    finally:
        paths["exercise_md_path"].chmod(0o644)


def test_plan_marks_lifestyle_sources_not_configured_by_default(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir)

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    sources = json.loads((repo_root / ".state" / "profiles" / "test-user" / "sources.json").read_text())
    assert sources["sources"]["schedule_md_path"]["status"] == "not configured"
    assert sources["sources"]["nutrition_md_path"]["status"] == "not configured"
    assert sources["sources"]["exercise_md_path"]["status"] == "not configured"
    assert sources["sources"]["lifestyle_constraints_md_path"]["status"] == "not configured"


def test_daily_plan_applies_sidecar_constraints_without_copying_them(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir, lifestyle_sources=True)

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "daily-plan",
            "--profile",
            "test-user",
            "--date",
            "2026-04-16",
        ]
    )

    assert exit_code == 0
    report_path = repo_root / ".output" / "test-user" / "2026-04-16-test-user-daily-plan.md"
    report_text = report_path.read_text(encoding="utf-8")
    assert "banana" not in report_text
    assert "excluded because they matched the sidecar constraint source" in report_text
    assert "Exercise template time overlaps a fixed schedule block" in report_text
    assert "Sidecar constraints are read from `lifestyle_constraints_md_path`" in report_text


def test_plan_migrates_legacy_flat_issue_state_per_profile(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir, slug="alpha", display_name="Alpha User")
    _write_profile(home_dir, slug="beta", display_name="Beta User")

    _write_json(
        repo_root / ".state" / "issues" / "alpha-issue.json",
        _issue_payload(
            profile_slug="alpha",
            title="Alpha Issue",
            confidence_frame="differential",
            next_best_action="Book hematology.",
            why="High-yield next step.",
        ),
    )
    _write_json(
        repo_root / ".state" / "issues" / "beta-issue.json",
        _issue_payload(
            profile_slug="beta",
            title="Beta Issue",
            confidence_frame="likely diagnosis",
            next_best_action="Book gastroenterology.",
            why="Profile-specific follow-up.",
        ),
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "alpha",
        ]
    )

    assert exit_code == 0
    issues = json.loads((repo_root / ".state" / "profiles" / "alpha" / "issues.json").read_text())
    assert [issue["slug"] for issue in issues["issues"]] == ["alpha-issue"]
    actions = json.loads((repo_root / ".state" / "profiles" / "alpha" / "actions.json").read_text())
    assert actions["actions"][0]["issue_slug"] == "alpha-issue"


def test_plan_issues_from_directory_only_imports_matching_profile(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir, slug="alpha", display_name="Alpha User")
    _write_profile(home_dir, slug="beta", display_name="Beta User")

    import_dir = repo_root / "issue-import"
    _write_json(
        import_dir / "alpha-issue.json",
        _issue_payload(
            profile_slug="alpha",
            title="Alpha Issue",
            confidence_frame="differential",
            next_best_action="Book hematology.",
            why="High-yield next step.",
        ),
    )
    _write_json(
        import_dir / "beta-issue.json",
        _issue_payload(
            profile_slug="beta",
            title="Beta Issue",
            confidence_frame="likely diagnosis",
            next_best_action="Book gastroenterology.",
            why="Profile-specific follow-up.",
        ),
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "plan",
            "--profile",
            "alpha",
            "--issues-from",
            str(import_dir),
        ]
    )

    assert exit_code == 0
    issues = json.loads((repo_root / ".state" / "profiles" / "alpha" / "issues.json").read_text())
    assert [issue["slug"] for issue in issues["issues"]] == ["alpha-issue"]
    actions = json.loads((repo_root / ".state" / "profiles" / "alpha" / "actions.json").read_text())
    assert [action["issue_slug"] for action in actions["actions"]] == ["alpha-issue"]


def test_outcome_update_alias_rescans_without_manual_event_file(
    tmp_path: Path, capsys
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    _write_profile(home_dir)

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--home-dir",
            str(home_dir),
            "outcome-update",
            "--profile",
            "test-user",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "deprecated" in captured.out
    assert (repo_root / ".state" / "profiles" / "test-user" / "sources.json").exists()


def test_docs_match_skill_first_workflow() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    agents = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    skill = (
        repo_root / ".codex" / "skills" / "what-next-report" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "Use the what-next-report skill for profile myname" in readme
    assert "The canonical interface is the `what-next-report` skill through the agent." in readme
    assert "`unresolved-issue-review`" not in readme
    assert "The normal user-facing entrypoint for this repo is the agent invoking the relevant project skill" in agents
    assert "The skill itself is the primary interface." in skill

    for content in (readme, agents, skill):
        assert "outcome-update --profile" not in content
        assert "healthpilot review --profile" not in content
