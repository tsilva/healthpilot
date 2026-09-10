<div align="center">
  <img src="./logo.png" alt="healthpilot" width="420" />

  # healthpilot

  **🧭 Turn parsed health records into ranked next steps 🧭**
</div>

healthpilot is a local, file-based workflow for turning parsed health records into ranked next steps. It connects runtime profiles, labs, exams, health-log entries, medications, supplements, lifestyle notes, genetics, and project Codex skills into one longitudinal planning loop.

The canonical interface is the `healthpilot-report-what-next` skill through the agent. The Python CLI exists as deterministic support for rescans, evidence packets, cached SNP lookups, and draft daily plans.

## Install

```bash
git clone https://github.com/tsilva/healthpilot.git
cd healthpilot
python3 -m pip install -e ".[dev]"
```

Create a runtime profile outside the repo:

```bash
mkdir -p ~/.config/healthpilot/profiles
cp profiles/template.yaml.example ~/.config/healthpilot/profiles/myname.yaml
```

Edit `~/.config/healthpilot/profiles/myname.yaml` so it points at the parser outputs and optional source files for that profile.

Each person has a Markdown context file for goals, constraints, preferences, priorities, and other information that should guide their analysis:

```bash
cp profiles/context.md.example ~/.config/healthpilot/profiles/myname.md
```

Set `data_sources.profile_context_md_path` in their YAML to that file. For example, record a target weight with its status, date, and rationale under Goals, separate from measured weight. The agent reads the full file for every profile-specific analysis; deterministic evidence snapshots and packets include its coverage and summary. Daily drafts apply its supported food and schedule constraints. This is free-form personal guidance, not automated goal-progress tracking.

The context file is read-only during ordinary analysis and is the single authority for personal goals, constraints, preferences, and priorities. Every live profile must link its own file. Missing or unconfigured context is reported explicitly. Nutrition and exercise files remain operational templates governed by the context file; they are not separate stores of personal guidance.

Then invoke the agent from this repo with a prompt like:

```text
Use the healthpilot-report-what-next skill for profile myname and write the refreshed next-steps report.
```

Reports are bucketed under `.output/<profile_slug>/<report_type>/` and every filename starts with `<YYYY-MM-DD>-`. For example, what-next reports live at `.output/<profile_slug>/what-next/<YYYY-MM-DD>-<profile_slug>-action-plan.md`. Reports open with a decision layer, show changes since the prior comparable report, and keep source coverage and audit detail in an evidence appendix. What-next reports also include current status, a Now/Next/Later action board, and researched self-experiments when defensible.

## Routine calendar

Live schedules come from the Google Calendar plugin. Store each person's verified calendar ID, name, and timezone in their YAML profile under `data_sources.routine_calendar` (`calendar_id`, `name`, `timezone`). Personal context holds related preferences and constraints. The agent checks that calendar for relevant dates, including recurring instances and exceptions, before proposing meal or exercise times. Calendar changes require an explicit request. There is no schedule Markdown source or fallback.

The Python CLI does not fetch plugin events. Its daily draft explicitly marks calendar coverage as unchecked; the agent retrieves calendar events separately. Missing access or an unlinked calendar must be reported, and one person's calendar must never be used for another profile.

## Personal food plans

Use `$healthpilot-update-food-plan` for a selected profile to review constraints, recent health-log symptoms, representative Google Health expenditure/weight/activity/sleep and routine, then update the menu and its one-page PDF. The [local skill](.codex/skills/healthpilot-update-food-plan/SKILL.md) keeps the latest PDF at **`.output/<profile_slug>/daily-plan/food-plan.pdf`**; this path stays the same across updates. Dated archives are optional. Missing wearable data is disclosed, and calorie targets remain provisional when the evidence cannot support adjustment.

Each person's canonical food plan lives at `~/.config/healthpilot/profiles/<profile_slug>.food-plan.md`, linked through `data_sources.nutrition_md_path`. Ask the agent to bootstrap it for a selected profile. [The food-plan template](profiles/food-plan.md.example) supplies the structure; it is not a prescribed diet.

Whenever you add or change a goal, constraint, or preference, the agent updates that person's context first. Food-relevant changes also update their existing food plan. Every food-plan revision reads the full context and checks meals, portions, timing, and substitutions against it. Goals remain authoritative in context, with any target copied into the plan clearly dated. These explicit edits are allowed; clinical records and parser outputs remain read-only. Other people's plans are created only when requested.

## Commands

```bash
pytest                                      # run tests
./sync.sh                                   # sync every live profile
./sync.sh --profile myname                  # sync one live profile
healthpilot plan --profile myname          # refresh deterministic evidence and state
healthpilot evidence-packet --profile myname
healthpilot daily-plan --profile myname --date 2026-04-29
healthpilot selfdecode-genotypes --profile myname --rsids rs429358 rs7412
healthpilot validate-report --type what-next --report .output/myname/what-next/2026-08-11-myname-action-plan.md
healthpilot migrate-output-layout            # dry-run manifest
healthpilot migrate-output-layout --apply    # migrate recognized history
```

Deprecated aliases such as `healthpilot intake`, `healthpilot review`, and `healthpilot outcome-update` still route to `plan` for compatibility.

## Notes

- Requires Python 3.11 or newer.
- Runtime profiles live in `~/.config/healthpilot/profiles/`; repo-local `profiles/*.yaml` are development references only.
- Optional API keys belong in `~/.config/healthpilot/.env`; `.env.example` documents the supported `NCBI_API_KEY`.
- Clinical records and parser outputs are read-only. Context and canonical food plans can be updated as described above; other lifestyle sources remain read-only.
- Derived state lives under `.state/profiles/<profile_slug>/`; user-facing reports live under `.output/<profile_slug>/<report_type>/`.
- Evidence packets use report-safe citation IDs in user-facing artifacts while retaining private path resolution under `.state/`.
- The primary data sources are `labs-parser`, `medical-exams-parser`, `health-log-parser`, optional raw 23andMe data, optional SelfDecode genotype lookups, and optional lifestyle Markdown files.
- Optional Google Health wearable evidence uses one shared Desktop OAuth app and profile-isolated credentials/cache under `~/.config/healthpilot/google-health/`. See [setup, retrieval, and report integration](docs/google-health.md). Unconnected profiles continue to work.
- SelfDecode JWTs are transient credentials. The cache stores genotype results only, in `.state/profiles/<profile_slug>/selfdecode-genotypes.json`.
- Project report skills live under `.codex/skills/` and share the `healthpilot-report-` prefix: `healthpilot-report-what-next`, `healthpilot-report-root-cause`, `healthpilot-report-treatment-record`, `healthpilot-report-organ-system-health`, `healthpilot-report-mortality-risk`, and `healthpilot-report-doctor-appointment`.
- Printable colour-coded medication tables use `healthpilot-medication-sheet`. The skill reconciles the current regimen for a selected live profile and writes a one-page PDF under `.output/<profile_slug>/treatment-record/` without modifying profile-linked source files.
- Profile gap-filling uses `healthpilot-profile-interview`, which asks high-yield questions and creates a paste-ready health-log entry rather than a report.
- Appointment preparation uses `healthpilot-report-doctor-appointment`. It creates a facts-only one-page clinician PDF and a detailed patient PDF with the relevant printable labs, exams, imaging, or other supporting records merged into it. For a confirmed repeat visit with the same named clinician, the handout highlights only what is new since the latest completed visit.

## Architecture

![healthpilot architecture diagram](./architecture.png)

## License

[MIT](LICENSE)
