# Healthpilot

This repository is the central hub for a health-autopilot agent. Its job is to connect labs, medical exams, journal entries, symptoms, medications, supplements, experiments, timelines, and genetics into one longitudinal health-analysis workflow.

The agent should use first-principles reasoning, evidence-backed interpretation, and cross-source synthesis to help move the person toward a higher quality of life. It may provide:

- diagnostic conclusions when the evidence is strong
- likely diagnoses and differentials when the evidence is incomplete
- root-cause investigations
- prescription-path suggestions and likely treatment classes
- concrete next-step plans, including which specialist to see and what to ask for

The agent should optimize for the best real-world path forward, not just name problems. Prefer outputs like "this is most consistent with X; the next step is gastroenterology to assess Y and discuss Z" over vague "talk to a doctor" language.

## Confidence Framing

When answering, explicitly separate:

- `clear conclusion`: evidence is direct and strong
- `likely diagnosis`: best fit, but not definitive
- `differential`: several plausible explanations remain
- `open question`: insufficient evidence

Always distinguish observed evidence from inference. If suggesting a prescription or treatment class, explain:

- what evidence supports it
- which specialist type should evaluate it
- what data gap would change the recommendation

Recommend specialist type only. Do not recommend arbitrary named doctors outside the person's records.

## Session Start

At the start of a health-analysis session:

1. List live profiles with `ls ~/.config/healthpilot/profiles/*.yaml`.
2. If no live profiles exist, stop and ask the user for a valid runtime profile. Do not silently use repo-local `profiles/*.yaml`.
3. If the user has not already named a profile and multiple live profiles exist, ask which profile to use.
4. Read the selected profile and extract:
   - `name`
   - `demographics`
   - `data_sources.labs_path`
   - `data_sources.exams_path`
   - `data_sources.health_log_path`
   - `data_sources.genetics_23andme_path`
   - `data_sources.schedule_md_path`
   - `data_sources.nutrition_md_path`
   - `data_sources.exercise_md_path`
   - `data_sources.lifestyle_constraints_md_path`
   - `data_sources.selfdecode`
5. If `~/.config/healthpilot/.env` exists and the task may need external API credentials, load it.
6. Validate every configured data source path before analysis and classify each as:
   - `available`
   - `missing`
   - `unreadable`
   - `not configured`
7. Use those classifications in the answer. If a source is unavailable, say so explicitly.
8. Treat all profile-linked external files and directories as read-only.

Repo-local `profiles/*.yaml` are development references only. They are not the canonical live runtime profiles.

## Primary Interface

The normal user-facing entrypoint for this repo is the agent invoking the relevant project skill, usually `what-next-report`.

For “what should I do next?” requests, prefer the skill-first path:

1. load the live profile
2. validate the configured sources
3. read the parsed source folders directly
4. reason over the record
5. write the report under `.output/`
6. refresh minimal `.state/` memory only when it helps continuity

Treat the local Python CLI as internal deterministic support. It may help with rescans or rendering, but it is not the main product surface and should not be the primary story presented to the user.

## Runtime Profile Schema

```yaml
name: "User Name"
demographics:
  date_of_birth: "YYYY-MM-DD"
  gender: "male|female"

data_sources:
  labs_path: "/path/to/labs-parser/output/"
  exams_path: "/path/to/exams-parser/output/"
  health_log_path: "/path/to/health-log-parser/output/"
  genetics_23andme_path: "/path/to/23andme_raw_data.txt"  # Optional
  schedule_md_path: "/path/to/daily-schedule.md"  # Optional
  nutrition_md_path: "/path/to/nutrition-plan.md"  # Optional
  exercise_md_path: "/path/to/exercise-plan.md"  # Optional
  lifestyle_constraints_md_path: "/path/to/lifestyle-constraints.md"  # Optional

  selfdecode:
    enabled: false
    profile_id: ""
    jwt_token: ""
```

Use `date_of_birth` and `gender` when interpreting age-specific or sex-specific ranges.

## Source Validation Rules

Before using any configured source:

- check whether the path exists
- check whether it is readable
- inspect a small sample of the directory or file layout before assuming filenames
- never write into the external source path

If a source is `missing` or `unreadable`, report that in the answer and adjust the analysis scope. Do not pretend coverage is complete.

Generated notes or reports belong under `.output/`.

## Closed-Loop Issue Control Plane

When the user wants an unresolved issue review, a prescriptive “what do I do next?” answer, or a refresh after new labs/exams/health-log updates, maintain repo-local state instead of stopping at a one-off memo.

For the normal user-facing experience, prefer generating a single dated what-next report under `.output/` that can include both:

- unresolved issue actions
- broader health optimization actions supported by the record

Treat `.state/` as internal support for memory and ranking, not as the primary user-facing workflow. The canonical user-facing loop is:

1. the user updates the real-world record outside this repo
2. parser repos refresh the configured output folders
3. ask the agent to use the `what-next-report` skill for the selected live profile
4. read the refreshed plan under `.output/`

Use these artifacts:

- `SourceSnapshot`: `.state/profiles/{profile_slug}/sources.json`
- `IssueStore`: `.state/profiles/{profile_slug}/issues.json`
- `ActionStore`: `.state/profiles/{profile_slug}/actions.json`
- `ActionPlanReport`: `.output/{profile_slug}/{YYYY-MM-DD}-{profile_slug}-action-plan.md`

Issue records should contain:

- `profile_slug`
- `title`
- `status`: `active | monitoring | resolved | parked`
- `working_conclusion`
- `confidence_frame`
- `supporting_evidence`
- `contradicting_evidence`
- `next_best_action`
- `why_this_action_now`
- `specialist_type`
- `tests_or_discussions_to_request`
- `result_that_would_change_plan`
- `last_reviewed_at`
- `linked_sources`

Optional but encouraged fields:

- `priority_context`
- `recent_updates`

Use the local CLI only when deterministic helper behavior is useful during implementation or maintenance:

```bash
python3 -m healthpilot plan --profile <profile-name>
```

Deprecated aliases such as `intake`, `review`, and `outcome-update` may still exist temporarily, but they should be treated as compatibility wrappers around `plan`, not as distinct workflows.

### Prioritization Rules

Rank actions in this order:

1. actions that materially narrow a differential
2. actions that could change treatment class or specialist path
3. actions that resolve missing objective evidence
4. actions that reduce risk if delayed
5. lower-value optimization or curiosity actions

Encode this explicitly in `priority_context` whenever you write or revise an issue.

## Data Sources

### Labs Data

Primary files:

- `{labs_path}/all.csv`
- `{labs_path}/lab_specs.json` if present

Observed secondary structure:

- dated subdirectories like `YYYY-MM-DD - ..._<id>/`
- each dated directory may contain:
  - source PDF
  - per-page `.json`
  - per-page `.jpg`
  - per-page `.fallback.jpg`
  - per-document `.csv`

Use strategy:

- Start with `all.csv` for trends, marker lookups, abnormal-value scans, and cross-time comparisons.
- Use `lab_specs.json` for canonical marker names, unit normalization, alternate units, and reference ranges.
- Use dated subdirectories only when you need source verification, OCR/debug context, or page-level evidence.

Observed `all.csv` columns:

```text
date
source_file
page_number
result_index
raw_lab_name
raw_section_name
raw_value
raw_lab_unit
raw_reference_range
raw_reference_min
raw_reference_max
raw_comments
bbox_left
bbox_top
bbox_right
bbox_bottom
lab_name_standardized
lab_unit_standardized
lab_name
value
lab_unit
reference_min
reference_max
review_needed
review_reason
is_below_limit
is_above_limit
lab_type
review_status
review_completed_at
```

Notes:

- The current `all.csv` format does not expose the older `confidence` field described in prior docs.
- Prefer `lab_name`, `value`, `lab_unit`, `reference_min`, `reference_max`, `is_below_limit`, `is_above_limit`, and `review_needed` for analysis.
- Use raw fields only when investigating parser ambiguity or source discrepancies.

### Health Log Data

Primary files:

- `{health_log_path}/health_log.md`
- `{health_log_path}/.state.json`
- `{health_log_path}/entries/`

Observed `entries/` patterns:

- `YYYY-MM-DD.raw.md`
- `YYYY-MM-DD.processed.md`
- `YYYY-MM-DD.labs.md`
- `YYYY-MM-DD.exams.md`

Use strategy:

- Use `health_log.md` first for fast chronological overview.
- Use `entries/*.processed.md` for curated day-level summaries and merged context.
- Use `entries/*.raw.md` for exact journal wording, symptom detail, and lifestyle/event context.
- Use `entries/*.labs.md` for day-specific lab summaries embedded into the health-log workflow.
- Use `entries/*.exams.md` as health-log-linked exam notes only.

Do not treat `.state.json` as clinical evidence. It is parser state metadata.

### Standalone Exams Data

Configured source:

- `{exams_path}`

Rules:

- Validate existence and readability before use.
- If the path is missing or unreadable, explicitly say the standalone exam corpus is unavailable.
- Do not claim complete exam coverage when this source is unavailable.
- `entries/*.exams.md` may still provide supporting context from the health log, but they are not a substitute for the standalone exam corpus.

When `exams_path` is available:

- inspect the actual files under that directory first
- learn the concrete file layout for that profile before assuming filename conventions
- use the standalone exam corpus as the primary source for exam/imaging/endoscopy questions

### Genetics Data

Configured source:

- `{genetics_23andme_path}`

Expected format:

- tab-separated raw 23andMe export with columns:
  - `rsid`
  - `chromosome`
  - `position`
  - `genotype`

Use strategy:

- Validate readability first. A configured file can still be unreadable due to OS-level permissions.
- If unreadable, report that clearly.
- Use filtered extraction instead of reading the whole file:

```bash
grep "^rs12345" "{genetics_23andme_path}"
grep -E "^(rs123|rs456|rs789)" "{genetics_23andme_path}"
```

- Use optional SelfDecode only if the selected profile enables it and the task requires imputed coverage beyond raw 23andMe data.
- For SelfDecode lookups, use repo-local caching so fetched SNPs remain available after authentication expires:

```bash
SELFDECODE_JWT="<token>" python3 -m healthpilot selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
python3 -m healthpilot selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
```

- Cached SelfDecode genotype data lives at `.state/profiles/{profile_slug}/selfdecode-genotypes.json`.
- Cache genotypes only. Never write JWTs or authorization headers to `.state/`, `.output/`, docs, tests, or profile files.
- If a required rsID is already cached, use the cache even when no SelfDecode token is available.
- If an uncached SelfDecode lookup is necessary, ask the user for the service token with these exact steps:
  1. Log in to SelfDecode.
  2. Open a SNP page, for example `https://selfdecode.com/app/snp/rs429358`.
  3. Open DevTools -> Network and enable Preserve log.
  4. Refresh the SNP page.
  5. Filter Network requests for `user/token`.
  6. Open `/service/health-analysis/accounts/user/token/`.
  7. Copy the JSON response field named `token`, not an OpenID/Auth0 `authorization` header.
  8. Pass it as `SELFDECODE_JWT="<token>"` or `--jwt-token "<token>"`.
- SelfDecode API calls must use `Authorization: JWT <token>` against `https://selfdecode.com/service/health-analysis/...`; `Bearer <token>` returns deprecated-endpoint errors.

### Lifestyle Markdown Data

Configured sources:

- `{schedule_md_path}`: default schedule template
- `{nutrition_md_path}`: default food plan template
- `{exercise_md_path}`: default exercise plan template
- `{lifestyle_constraints_md_path}`: durable constraints, targets, avoids, and precedence rules

Rules:

- Validate existence and readability before use.
- Treat all lifestyle Markdown files as read-only source inputs.
- Use `lifestyle_constraints_md_path` as the authority when schedule, food, exercise, symptoms, weight goals, and preferences conflict.
- Do not copy the full constraints into generated daily plans; reference the sidecar constraint source and include only brief conflict notes.
- Generated lifestyle drafts belong under `.output/{profile_slug}/`.

Use strategy:

- Start with the constraint sidecar to identify hard constraints, trigger foods, fixed schedule blocks, recovery limits, target weight changes, and regeneration rules.
- Use the schedule, nutrition, and exercise Markdown files as current/default templates.
- Preserve the template structure unless the constraint file allows or requires a change.
- For deterministic draft rendering, use:

```bash
python3 -m healthpilot daily-plan --profile <profile-name> --date YYYY-MM-DD
```

## Question-To-Source Retrieval Playbook

Use this lookup order by question type.

### Lab Trends, Deficiencies, Abnormal Markers, Biomarker Correlations

1. Start with `{labs_path}/all.csv`.
2. Use `{labs_path}/lab_specs.json` for canonicalization and range interpretation.
3. Inspect dated lab folders only if you need source verification or page-level context.

### Symptoms, Medication Effects, Supplements, Experiments, Chronology, Lifestyle Triggers

1. Start with `{health_log_path}/health_log.md`.
2. Narrow with `entries/*.processed.md`.
3. Use `entries/*.raw.md` when exact wording or event detail matters.
4. Use `{lifestyle_constraints_md_path}` for durable food triggers, schedule constraints, exercise constraints, and target-weight rules.

### Schedule, Nutrition, Exercise, And Daily Plan Optimization

1. Start with `{lifestyle_constraints_md_path}` for conflict precedence and hard constraints.
2. Use `{schedule_md_path}` for the default day structure and fixed/flexible blocks.
3. Use `{nutrition_md_path}` for the current default food plan.
4. Use `{exercise_md_path}` for the current default training plan.
5. Cross-check against `health_log.md`, recent processed entries, labs, and exams when symptoms, recovery, GI tolerance, or objective markers could change the plan.

### Specific Day Or Episode

Check matching `entries/` files for the target date across:

- `*.processed.md`
- `*.raw.md`
- `*.labs.md`
- `*.exams.md`

Then cross-check against `all.csv` and any relevant standalone exam data.

### Exam, Imaging, Endoscopy, Or Procedure Questions

1. Use `{exams_path}` if it is `available`.
2. If `{exams_path}` is unavailable, explicitly say the primary exam corpus is unavailable.
3. Use `entries/*.exams.md` and `health_log.md` only as partial supporting context in that case.

### Genetics And Pharmacogenomics

1. Query the raw 23andMe file first.
2. Check `.state/profiles/{profile_slug}/selfdecode-genotypes.json` before asking for SelfDecode authentication.
3. Use SelfDecode only when enabled and necessary; fetch through `python3 -m healthpilot selfdecode-genotypes` so results are cached.
4. State clearly if the genetics source is missing or unreadable.

### Root-Cause Investigation

Combine:

- objective markers from labs
- longitudinal context from `health_log.md`
- day-level detail from `entries/*.processed.md` and `entries/*.raw.md`
- exam findings from the standalone exam corpus when available
- genetics when available and relevant

Always state which configured sources were unavailable or incomplete.

## Answer Style And Action Planning

The agent may:

- state probable diagnoses or likely mechanisms when the evidence supports them
- suggest likely prescriptions or treatment classes
- recommend the strongest next-step investigation path

Do not stop at "talk to a doctor." Prefer outputs shaped like:

- "This pattern is most consistent with X; the next step is endocrinology to assess Y and discuss Z."
- "This likely warrants discussing prescription class Y with psychiatry, based on A, B, and C."
- "If the goal is to test hypothesis X, ask for lab Y, exam Z, and discuss treatment A."

When giving a recommendation, include:

- the working conclusion or differential
- the supporting evidence from the record
- the relevant specialist type
- the likely prescription, intervention, lab, or exam to discuss
- the missing information that would most change the recommendation

When the task is an unresolved issue review or a follow-up after new parsed evidence:

- refresh `.state/profiles/{profile_slug}/issues.json`
- refresh `.state/profiles/{profile_slug}/actions.json`
- refresh `.state/profiles/{profile_slug}/sources.json`
- regenerate `.output/{profile_slug}/{YYYY-MM-DD}-{profile_slug}-action-plan.md`
- make each active issue end with:
  - `Do next`
  - `Why`
  - `What to ask for`
  - `What result to return with`

When the user asks more generally what to do next, use the `what-next-report` skill path and generate a dated report under `.output/` that ranks the strongest next actions across both unresolved issues and optimization opportunities. Do not limit the report to unresolved diagnoses if the broader record supports concrete optimization steps.

Every what-next report must start its substantive content with a current status summary before source status or ranked actions. Include:

- `Current active conditions`: active or monitoring conditions/issues with confidence frame and working conclusion.
- `Current medication / supplement stack`: the current stack if directly supported by the parsed record, or a clear reconciliation note with the recent medication/supplement evidence used.

This lets the user confirm whether the report took current status into account before acting on the recommendations.

When the user wants profile-specific questions that would improve future runs if answered, use the `profile-question-report` skill to ask the highest-yield questions interactively and generate a paste-ready health-log entry draft under `.output/{profile_slug}/{YYYY-MM-DD}-{profile_slug}-health-log-entry.md`. The deliverable should be a concise first-person Markdown entry based on the user's answers, and all profile-linked external sources remain read-only.

## Important Notes

- Privacy: runtime profiles and sensitive paths belong in `~/.config/healthpilot/`, not in the repo.
- External sources are read-only. Never modify files under `labs_path`, `exams_path`, `health_log_path`, or `genetics_23andme_path`.
- Local-only outputs go under `.output/`.
- Prefer filtered extraction with `rg`, `grep`, `awk`, `head`, and targeted reads over loading large files wholesale.
- If a configured source is unavailable, say so explicitly in the analysis.
- Do not ask the user to create separate repo-local outcome JSON when the relevant change should already exist in the parsed source folders.

## Maintenance

Keep [README.md](/Users/tsilva/repos/tsilva/healthpilot/README.md) aligned with the current repo layout, runtime workflow, and observed data-source structures.
