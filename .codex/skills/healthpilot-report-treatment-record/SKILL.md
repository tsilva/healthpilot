---
name: healthpilot-report-treatment-record
description: Generate a dated, evidence-reconciled treatment record covering current medications, supplements, therapies, devices, lifestyle treatments, monitoring, planned or unclear items, recently completed treatments, and longitudinal medication or supplement history for a selected live Healthpilot profile. Use when the user asks for current meds, an active regimen, medication reconciliation, a treatment list, a supplement list, past medications, medication history, treatment history, or a treatment timeline.
---

# Treatment Record

Generate every user-facing report and companion artifact in European Portuguese (`pt-PT`), following the shared report contract's language rules.

Create one treatment record that answers both present-tense reconciliation and historical medication or supplement questions. Put the current regimen first, keep noncurrent items visibly separate, and preserve a compact longitudinal history.

## Required session rules

1. Follow the live-profile selection and source-validation rules in `AGENTS.md`.
2. Treat every profile-linked source as read-only.
3. Write the report under `.output/{profile_slug}/treatment-record/`.
4. Use `.state/` and prior reports only as retrieval support; verify status in canonical sources.
5. Distinguish observed evidence from inference. Do not invent dose, route, frequency, indication, prescriber, adherence, response, start date, or stop date.
6. Reconcile the record; do not recommend treatment changes unless the user separately asks for advice.

## Scope

Include supported items from these categories:

- prescription, over-the-counter, rescue, and intermittent medications
- vitamins, minerals, herbs, performance products, and other supplements
- psychotherapy, physiotherapy, rehabilitation, injections, infusions, wound care, and other clinical therapies
- devices such as CPAP, braces, compression garments, monitors, or assistive equipment
- clinician-directed or clearly active nutrition, exercise, sleep, recovery, and behavioral treatments
- self-directed experiments, labeled as self-directed
- treatment-linked monitoring and surveillance

Do not classify an ordinary food, isolated behavior, historical procedure, diagnosis, test, or future appointment as treatment unless the record explicitly makes it part of a regimen.

## Retrieval workflow

1. Load the selected live profile and classify every configured source as `available`, `missing`, `unreadable`, or `not configured`.
2. Generate or refresh the factual evidence packet when helpful:

```bash
healthpilot evidence-packet --profile <profile-name>
python3 -m healthpilot evidence-packet --profile <profile-name>
```

3. Start with explicit current-stack or regimen sections in `{health_log_path}/health_log.md`.
4. Read relevant `entries/*.processed.md` and targeted `entries/*.raw.md` to establish starts, dose changes, adherence, PRN use, response, adverse effects, stops, replacements, restarts, and whether a planned trial began.
5. Inspect the standalone exam corpus for medication lists, prescriptions, treatment plans, devices, therapies, monitoring, and documented discontinuations. Treat copied visit lists as evidence, not automatic proof of use.
6. Use `entries/*.exams.md` as supporting context, not a substitute for the standalone exam corpus.
7. Read configured nutrition, exercise, and personal-context Markdown, and retrieve the profile-linked routine calendar when timing matters. Treat templates as intended plans unless current evidence supports actual use.
8. Use labs only for treatment monitoring, response, or a treatment-linked timeline. A lab alone does not prove treatment use.
9. Use genetics only when the record explicitly links it to treatment selection or dosing.
10. Read `.state/profiles/{profile_slug}/evidence-packet.json`, `issues.json`, and `actions.json` when helpful, but treat planned actions as planned until canonical evidence confirms execution.
11. Add every configured source category to the coverage ledger.

Use targeted retrieval first. For a present-tense request, read older history only far enough to resolve current status and include material prior treatment context. For an explicit history request, retrieve the complete relevant medication and supplement timeline without padding it with unrelated care.

## Reconciliation statuses

Assign exactly one current reconciliation status to every item:

- `confirmed active`
- `likely active`
- `active PRN/intermittent`
- `planned/recommended—not confirmed started`
- `unclear—needs reconciliation`
- `recently stopped/completed`
- `historical—not current`

Only the first three statuses belong in current-treatment tables.

Apply these precedence rules:

1. Prefer the latest explicit start, continuation, dose change, stop, or nonadherence statement over older lists.
2. Prefer a dated statement of actual use over a copied-forward medication list when they conflict, while preserving the conflict.
3. Do not equate `prescribed`, `recommended`, `ordered`, `consider`, `discuss`, or `plan to start` with started.
4. Treat a finite course as completed after its documented duration unless later evidence supports continuation.
5. Treat PRN use as current only when continued intended availability or use is supported.
6. Preserve unresolved dose, route, frequency, ingredient, and stop-date conflicts.
7. Deduplicate clear synonyms and brand/generic pairs without merging materially different formulations.
8. Label origin as `prescribed`, `clinician-directed`, `self-directed`, or `unclear` only when supported.

Use `conclusão clara` for directly supported current or historical status and `questão em aberto` for uncertainty. Do not force diagnostic confidence labels onto reconciliation.

## Report contract

Read [references/report-template.md](references/report-template.md) before drafting.
Read [../_shared/healthpilot-report-contract.md](../_shared/healthpilot-report-contract.md) and apply it in full.

Start the decision layer with `## Regime atual em resumo`. Show confirmed current treatment, material recent changes, reconciliation conflicts, and the most urgent confirmation need before the detailed treatment tables.

For every current medication or supplement, include when available:

- normalized and recorded name
- reconciliation status
- dose, formulation, route, frequency, and timing
- origin and stated target, labeling inferred targets
- earliest supported current use and latest confirmation
- adherence, response, and adverse effects
- direct source citation

For non-medication treatments, include category, protocol, target, origin, latest confirmation, adherence, response, and evidence.

Keep planned items, unclear items, and recently completed items outside the current tables. In `Histórico de medicação e suplementos`, summarize meaningful starts, dose changes, pauses, restarts, stops, replacements, responses, and adverse effects with dates. Do not repeat the full current row when a short cross-reference is sufficient.

## Reconciliation and safety

- Surface dose conflicts, duplicate listings, ingredient overlap, recorded allergies, adverse effects, missed monitoring, and ambiguous instructions as reconciliation flags.
- Do not diagnose an interaction or contraindication without researching it and labeling that analysis separately.
- Never tell the user to start, stop, taper, or change treatment in this record.
- If canonical evidence documents an acute severe reaction or dangerous administration error, add a concise urgent safety note and identify the appropriate care level.
- If no current items are supported, say so explicitly instead of promoting historical mentions into the current regimen.

## Output and validation

- directory: `.output/{profile_slug}/treatment-record/`
- filename: `{YYYY-MM-DD}-{profile_slug}-treatment-record.md`
- canonical path: `.output/{profile_slug}/treatment-record/{YYYY-MM-DD}-{profile_slug}-treatment-record.md`

Use the local report date and canonical profile slug. Refresh the same-day canonical file instead of creating an alternate filename.

Validate the finished report:

```bash
python3 -m healthpilot validate-report \
  --type treatment-record \
  --report .output/{profile_slug}/treatment-record/{YYYY-MM-DD}-{profile_slug}-treatment-record.md \
  [--previous .output/{profile_slug}/treatment-record/{previous-filename}]

python3 .codex/skills/healthpilot-report-treatment-record/scripts/validate_report.py \
  .output/{profile_slug}/treatment-record/{YYYY-MM-DD}-{profile_slug}-treatment-record.md
```

Fix every validator error. In the user-facing answer, link the report and summarize the current item count, historical item count, record cutoff, source gaps, and most important reconciliation question.
