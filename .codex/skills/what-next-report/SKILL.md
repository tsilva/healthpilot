---
name: what-next-report
description: Generate a dated what-next report for a selected live health-agent profile. Use when the user wants a prescriptive "what should I do next?" answer, a current action report, or an updated report after new labs, exams, visit feedback, or symptom changes. The report should include both unresolved-issue actions and health-optimization actions when the data supports them.
---

# What Next Report

This is the canonical high-level workflow for the repo.

When the user invokes this skill, the expected output is simple:

- read the selected live profile
- validate the configured sources
- generate/read the deterministic evidence packet from the current parsed source folders
- synthesize the best next actions from the record
- write one dated report under `.output/`

State files under `.state/` are implementation details. Use them when helpful, but do not make the user think about them unless they explicitly ask.

The expected user experience is simple: they ask the agent for next steps, this skill does the end-to-end work, and the report appears under `.output/`.

## Goals

- generate a single prescriptive report that answers "what should I do next?"
- include unresolved-issue actions when the record supports them
- also include broader health-optimization actions when they are actionable and evidence-backed
- keep outputs concise, ranked, and easy to follow

## Required Session Rules

1. Follow the profile and source-validation rules from `AGENTS.md`.
2. Treat external profile-linked sources as read-only.
3. Write the user-facing report under `.output/`.
4. Use `.state/` only as internal memory or ranking support.

## Working Order

Default to the shortest path that still produces a defensible current report.

1. Load the live profile and validate every configured source.
2. Generate or read the current evidence packet:

```bash
health-agent evidence-packet --profile <profile-name>
python3 -m health_agent evidence-packet --profile <profile-name>
```

3. Use `.state/profiles/{profile_slug}/evidence-packet.json` as the first evidence map. It is factual only: source status, freshness, changed files, lab/log/exam extracts, medication/supplement mention lines, lifestyle summaries, and issue/action memory.
4. Inspect the cited source snippets or files directly before making high-impact conclusions, especially diagnoses, medication/treatment-class suggestions, specialist direction, or surveillance timing.
5. If `.state/profiles/{profile_slug}/issues.json` and `.state/profiles/{profile_slug}/actions.json` already exist, use them as internal memory and refresh them only when current evidence changes conclusions, action ranking, or source citations.
6. If that state does not exist yet, do a first-run synthesis directly from the parsed record:
   - identify the main unresolved issues from the current evidence
   - write the report anyway on that first pass
   - optionally create `.state/profiles/{profile_slug}/issues.json`, `.state/profiles/{profile_slug}/actions.json`, and `.state/profiles/{profile_slug}/sources.json` after the reasoning is complete
   - do not stop just because repo-local state is empty
7. Pull older landmark findings only when they still change the current plan.
8. For SelfDecode SNP lookups, check `.state/profiles/{profile_slug}/selfdecode-genotypes.json` first and fetch missing rsIDs with the cache-aware helper:

```bash
python3 -m health_agent selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
SELFDECODE_JWT="<token>" python3 -m health_agent selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
```

If authentication is needed, tell the user to copy the `token` field from the `/service/health-analysis/accounts/user/token/` Network response on a logged-in SelfDecode SNP page. Never store JWTs; the helper caches genotypes only.
9. Do not detour into a broad historical reread unless the current evidence packet and current issue memory are too thin to rank next actions.
10. Use the built-in repo helper only as internal support when it reduces deterministic file work:

```bash
health-agent plan --profile <profile-name>
python3 -m health_agent plan --profile <profile-name>
```

Do not frame the CLI as the primary user interface. The skill itself is the primary interface.

## Output

Write a report named:

`{profile_slug}/{YYYY-MM-DD}-{profile_slug}-action-plan.md`

The durable repo-local artifacts for this workflow are:

- `EvidencePacket`: `.state/profiles/{profile_slug}/evidence-packet.json`
- `IssueStore`: `.state/profiles/{profile_slug}/issues.json`
- `ActionStore`: `.state/profiles/{profile_slug}/actions.json`
- `SourceSnapshot`: `.state/profiles/{profile_slug}/sources.json`
- `ActionPlanReport`: `.output/{profile_slug}/{YYYY-MM-DD}-{profile_slug}-action-plan.md`

The report should usually contain:

1. Title
2. `Report generated`
3. `Profile`
4. `Source status`
5. `Top next actions`
6. `Unresolved issues`
7. `Optimization opportunities`
8. `What to return with`

When lifestyle sources are configured, include them in source status and use `lifestyle_constraints_md_path` as the authority for conflicts between schedule, nutrition, exercise, symptom triggers, target weight changes, and preferences.

## Report Content Rules

### Top Next Actions

Rank the best actions across both categories:

- unresolved diagnosis or workup actions
- follow-up or surveillance actions
- treatment-discussion actions
- optimization actions for sleep, GI function, exercise, recovery, diet, or other high-value areas

Do not include vague filler. Prefer a short ranked list of concrete actions.

For each ranked action, include:

- `Do next`
- `Why`
- `What to ask for` or `What to do`
- `What to return with`

### Unresolved Issues

Include the important unresolved issues that materially affect health or decision-making.

For each issue, state:

- `working conclusion`
- `confidence frame`
- the strongest supporting evidence
- the next step that would most change the plan

### Optimization Opportunities

Include only if they are supported by the record and worth acting on now.

Examples:

- sleep optimization based on symptoms, sleep studies, or diary patterns
- GI optimization based on recurring symptoms and response patterns
- exercise or biomechanics changes when the record suggests a likely mechanical driver
- supplement or medication timing or trial cleanups when the record shows confusion or repeated unclear reactions
- meal timing, food substitutions, workout placement, or recovery changes when profile-linked lifestyle Markdown files provide concrete constraints

Do not pad the report with generic lifestyle advice.

### Lifestyle Constraints

If the profile configures lifestyle Markdown files:

- read `lifestyle_constraints_md_path` before changing schedule, nutrition, or exercise plans
- treat schedule, nutrition, and exercise Markdown files as current/default templates
- do not edit or rewrite the source Markdown files
- write regenerated draft plans under `.output/{profile_slug}/`
- avoid copying the full sidecar constraints into generated plans; include only short conflict notes and source references
- use `health-agent daily-plan --profile <profile-name> --date YYYY-MM-DD` as deterministic support when it helps render a draft daily plan

## Prioritization Rules

Rank actions in this order:

1. actions that materially narrow a differential
2. actions that could change treatment class or specialist path
3. actions that resolve missing objective evidence
4. actions that reduce risk if delayed
5. high-value optimization actions supported by the record
6. lower-value curiosity or cleanup actions

## Using Repo State

If durable issue records already exist under `.state/profiles/{profile_slug}/issues.json`, use them as memory and refresh them when helpful.

If repo state does not exist yet, the skill must still complete the task from the parsed source folders alone. Empty `.state/` is a normal first-run condition, not a blocker.

If the report clearly centers on unresolved issues, you may also update:

- `.state/profiles/{profile_slug}/issues.json`
- `.state/profiles/{profile_slug}/actions.json`
- `.state/profiles/{profile_slug}/sources.json`

But the primary deliverable is always the report in `.output/`.

When refreshing issue memory:

- identify the important unresolved issues from the current record
- keep `priority_context` explicit so ranking is encoded rather than implied
- preserve older evidence that still affects the current plan
- mark resolved issues as `resolved` instead of deleting them

Each issue record should:

- include `profile_slug`
- keep `linked_sources` as absolute file paths when possible
- keep citations current when evidence changes; these citations flow into action state as `source_citations`
- end in an operator-friendly format:
  - `Do next`
  - `Why`
  - `What to ask for`
  - `What result to return with`

Use `priority_context` to encode the ranking bucket directly:

- `materially_narrows_differential`
- `changes_treatment_or_specialist_path`
- `resolves_missing_objective_evidence`
- `reduces_risk_if_delayed`
- `is_lower_value_optimization`

## Update Mode

When the user brings a new lab, exam, or health-log update:

- revise the conclusions that actually changed
- keep the prior evidence that still matters
- rerank the next actions
- regenerate the dated what-next report

Treat the parsed source folders as the canonical input. Do not ask the user to create a separate repo-local outcome JSON file.
