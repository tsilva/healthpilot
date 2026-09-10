---
name: healthpilot-report-what-next
description: Generate a dated what-next report for a selected live healthpilot profile. Use when the user wants a prescriptive "what should I do next?" answer, a current action report, or an updated report after new labs, exams, visit feedback, or symptom changes. The report should include both unresolved-issue actions and health-optimization actions when the data supports them.
---

# What Next Report

Generate every user-facing report and companion artifact in European Portuguese (`pt-PT`), following the shared report contract's language rules.

This is the canonical high-level workflow for the repo.

When the user invokes this skill, the expected output is simple:

- read the selected live profile
- validate the configured sources
- generate/read the deterministic evidence packet from the current parsed source folders
- synthesize the best next actions from the record
- write one dated report under `.output/{profile_slug}/what-next/`

State files under `.state/` are implementation details. Use them when helpful, but do not make the user think about them unless they explicitly ask.

The expected user experience is simple: they ask the agent for next steps, this skill does the end-to-end work, and the report appears under `.output/{profile_slug}/what-next/`.

## Goals

- generate a single prescriptive report that answers "what should I do next?"
- include unresolved-issue actions when the record supports them
- also include broader health-optimization actions when they are actionable and evidence-backed
- include researched self-experiments that the user can run independently when they have a favorable expected return, burden, safety, and measurability profile
- keep outputs concise, ranked, and easy to follow

## Required Session Rules

1. Follow the profile and source-validation rules from `AGENTS.md`.
2. Treat external profile-linked sources as read-only.
3. Write the user-facing report under `.output/{profile_slug}/what-next/`.
4. Use `.state/` only as internal memory or ranking support.

## Working Order

Default to the shortest path that still produces a defensible current report.

1. Load the live profile and validate every configured source.
2. Generate or read the current evidence packet:

```bash
healthpilot evidence-packet --profile <profile-name>
python3 -m healthpilot evidence-packet --profile <profile-name>
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
python3 -m healthpilot selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
SELFDECODE_JWT="<token>" python3 -m healthpilot selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
```

If authentication is needed, tell the user to copy the `token` field from the `/service/health-analysis/accounts/user/token/` Network response on a logged-in SelfDecode SNP page. Never store JWTs; the helper caches genotypes only.
9. Do not detour into a broad historical reread unless the current evidence packet and current issue memory are too thin to rank next actions.
10. Use the built-in repo helper only when refreshing deterministic evidence, issue, source, and action state helps:

```bash
healthpilot plan --profile <profile-name>
python3 -m healthpilot plan --profile <profile-name>
```

The CLI does not render the user-facing action plan. Do not frame it as the primary interface or expect it to create the Markdown report. The skill itself is the primary interface. It is the sole owner of the canonical action-plan file.

## Output Contract

Read [references/report-template.md](references/report-template.md) before drafting.
Read [../_shared/healthpilot-report-contract.md](../_shared/healthpilot-report-contract.md) and apply it in full.

Follow the common Healthpilot report convention:

- directory: `.output/{profile_slug}/what-next/`
- filename: `{YYYY-MM-DD}-{profile_slug}-action-plan.md`
- canonical path: `.output/{profile_slug}/what-next/{YYYY-MM-DD}-{profile_slug}-action-plan.md`

Use the local report date and canonical profile slug. Create the profile output directory when needed. If regenerating on the same date, refresh the canonical file instead of creating an alternate filename.

The durable repo-local artifacts for this workflow are:

- `EvidencePacket`: `.state/profiles/{profile_slug}/evidence-packet.json`
- `IssueStore`: `.state/profiles/{profile_slug}/issues.json`
- `ActionStore`: `.state/profiles/{profile_slug}/actions.json`
- `SourceSnapshot`: `.state/profiles/{profile_slug}/sources.json`
- `ActionPlanReport`: `.output/{profile_slug}/what-next/{YYYY-MM-DD}-{profile_slug}-action-plan.md`

The report must contain, in this order:

1. Title
2. Required shared metadata
3. `Estado atual`
4. `Agora / A seguir / Mais tarde`
5. `Alterações desde o relatório anterior`
6. `Autoexperiências ordenadas por retorno esperado`
7. `Questões por resolver`
8. `Oportunidades de otimização`
9. `O que trazer na próxima atualização`
10. `Apêndice de evidência`

The first substantive report section must be `Estado atual`, with:

- `Condições ativas atuais`: active or monitoring conditions/issues, including confidence frame and working conclusion.
- `Medicação e suplementos atuais`: the current stack if the record supports it, or a clear reconciliation note plus the recent medication/supplement evidence used.

This section exists so the user can immediately confirm whether the report took the current status into account before reading the action plan.

When lifestyle sources are configured, include them in source coverage and use `profile_context_md_path` as the authority for conflicts between schedule, nutrition, exercise, symptom triggers, target weight changes, and preferences.

## Report Content Rules

### Current Status Summary

Start every what-next report with `## Estado atual`. It must precede the action board and evidence appendix.

Use observed evidence for medication and supplement status. If the parsed record only contains medication/supplement mentions or recent changes rather than a reconciled active list, say that directly and list the evidence that needs reconciliation instead of pretending it is a confirmed current stack.

Keep this summary compact. For a full reconciliation or history request, use `healthpilot-report-treatment-record` rather than expanding the action plan into a second treatment record.

### Agora / A seguir / Mais tarde

Use a compact action board with these columns:

- `Rank`
- `Horizon`: `Now (0–7 days)`, `Next (8–30 days)`, or `Later / monitor`
- `Status`: `ready`, `waiting`, `scheduled`, or `done`
- `Action`
- `Done when`
- `Return with`

Put blocking dependencies in the detailed action text instead of adding vague priority labels.

### Source Coverage

Put one coverage table inside `## Apêndice de evidência`. Include source status, freshness or span, material evidence used, limitations, and an explicit `Fontes indisponíveis` statement. Do not add a second source-status list.

### Top Next Actions

Rank the best actions across both clinician-facing and self-directed categories:

- unresolved diagnosis or workup actions
- follow-up or surveillance actions
- treatment-discussion actions
- high-ROI self-experiments the user can run independently
- optimization actions for sleep, GI function, exercise, recovery, diet, or other high-value areas

Do not include vague filler. Prefer a short ranked list of concrete actions.

For each ranked action, include:

- `Do next`
- `Why`
- `What to ask for` or `What to do`
- `What to return with`

Self-directed experiments can appear in `Top Next Actions` when their expected return is high enough, but do not let them displace time-sensitive medical workups, actions that materially narrow a differential, or actions that could change a treatment class. When an experiment also appears in the dedicated ROI section, keep the top action compact and refer to its ROI rank instead of repeating the protocol.

### Self-Experiments Ranked By ROI

Every what-next report should include this section unless there are no defensible self-directed experiments to recommend right now. These are things the user can do independently to improve health or quality of life, including supplements, lifestyle changes, diet timing, exercise or recovery changes, sleep interventions, symptom-trigger avoidance, tracking protocols, environmental changes, or low-risk devices/tools.

Only include experiments that are researched and tailored to the profile. Use the user's record first, then current medical literature, guidelines, or reputable evidence summaries when the claim depends on external evidence. Cite the evidence briefly enough that the user can audit why the experiment made the list.

Rank experiments by practical ROI, blending:

- expected benefit for this profile's active issues, symptoms, goals, and constraints
- ease of execution and adherence burden
- cost, time requirement, and reversibility
- safety margin, interaction risk, and downside if wrong
- speed and clarity of feedback
- measurability with available symptoms, logs, wearables, labs, or repeatable observations
- strength and relevance of evidence

For each experiment, include:

- `ROI rank`
- `Hypothesis`
- `What to do`
- `Duration`
- `How to measure success`
- `Stop / avoid if`
- `Why this is worth trying now`
- `Evidence basis`
- `Expected ROI`

Prefer cheap, low-friction experiments with plausible high upside before expensive, complex, or ambiguous experiments. Avoid generic wellness filler. Avoid unsafe self-treatment, prescription-only interventions, aggressive supplement stacks, or experiments that could obscure an active diagnostic workup. For supplements, mention relevant medication interactions, lab-monitoring considerations, and conditions that would make the experiment inappropriate.

### Unresolved Issues

Include the important unresolved issues that materially affect health or decision-making.

For each issue, state:

- `working conclusion`
- `confidence frame`
- the strongest supporting evidence
- the next step that would most change the plan

If an issue already drives a ranked action, reference that action rank and do not repeat its `Do next`, `Why`, `What to ask for`, or `What to return with` fields. Use the issue section for evidence, counterevidence, confidence, and the unresolved data gap.

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

- read `profile_context_md_path` before changing schedule, nutrition, or exercise plans
- treat nutrition and exercise Markdown files as current/default templates; retrieve routine timing through the profile-linked Google Calendar calendar
- do not edit or rewrite the source Markdown files
- write regenerated draft plans under `.output/{profile_slug}/daily-plan/`
- avoid copying the full personal context into generated plans; include only short conflict notes and source references
- use `healthpilot daily-plan --profile <profile-name> --date YYYY-MM-DD` as deterministic support when it helps render a draft daily plan

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

But the primary deliverable is always the report in `.output/{profile_slug}/what-next/`.

When refreshing issue memory:

- identify the important unresolved issues from the current record
- keep `priority_context` explicit so ranking is encoded rather than implied
- preserve older evidence that still affects the current plan
- mark resolved issues as `resolved` instead of deleting them

Each issue record should:

- include `profile_slug`
- keep `linked_sources` as absolute file paths when possible
- keep citations current when evidence changes; these citations flow into action state as `source_citations`
- resolve internal paths through the evidence packet's `citation_index` and print only report-safe citation IDs in the report
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

## Validation

Run the shared validator before handoff:

```bash
python3 -m healthpilot validate-report \
  --type what-next \
  --report .output/{profile_slug}/what-next/{YYYY-MM-DD}-{profile_slug}-action-plan.md \
  [--previous .output/{profile_slug}/what-next/{previous-filename}]
```

Fix every error before returning the report.
