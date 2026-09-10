---
name: healthpilot-report-mortality-risk
description: Generate a dated, profile-specific report ranking the 10 most likely underlying causes of death, with calibrated probability estimates, plausible ranges, an explicit residual bucket, source coverage, and prevention priorities. Use when the user asks about personalized mortality risk, likely causes of death, cause-specific lifetime risk, or a probability-ranked mortality forecast for a live Healthpilot profile.
---

# Mortality Risk Report

Generate every user-facing report and companion artifact in European Portuguese (`pt-PT`), following the shared report contract's language rules.

Generate a cautious, evidence-auditable mortality-risk report from every available source category linked by a selected live Healthpilot profile. Treat the result as a baseline-calibrated risk estimate, not a prediction of how or when the person will die.

## Required Session Rules

1. Follow the live-profile selection and source-validation rules in `AGENTS.md`.
2. Treat all profile-linked external sources as read-only.
3. Write the report under `.output/{profile_slug}/mortality-risk/`.
4. Use `.state/` only as factual memory or retrieval support.
5. Browse for current official mortality statistics and current primary or authoritative evidence when estimating probabilities. Cite the data year and access date.
6. Distinguish observed evidence, population baseline, model output, and inference.
7. Never use this report for insurance, employment, eligibility, rationing, or emergency-triage decisions.

## Probability Contract

Default to the person's remaining lifetime from the report date. Define each ranked percentage as:

> Estimated probability that this mutually exclusive category will be the underlying cause of the person's eventual death, conditional on the current record, current population data, and stated modeling assumptions.

Do not imply a date of death. Do not label a lifetime cause share as a 10-year absolute risk.

If the user specifies a different horizon, honor it and state whether the percentages are:

- absolute cause-specific probabilities during that horizon, or
- conditional shares among deaths occurring during that horizon.

Do not mix these quantities. Add a separate all-cause horizon probability only when a validated model or defensible life-table calculation supports it. Never obtain it by multiplying a lifetime cause share by an unrelated all-cause risk.

## Complete Data Coverage

Consider every configured source category that is `available`; do not silently omit one. Add a source-coverage ledger showing status, freshness, material evidence used, and limitations.

1. Load the selected live profile and calculate current age from `date_of_birth` on the report date.
2. Validate and classify labs, exams, health log, genetics, nutrition, exercise, personal context, and SelfDecode configuration; check profile-linked calendar coverage when relevant.
3. Generate or refresh the factual evidence packet when helpful:

```bash
healthpilot evidence-packet --profile <profile-name>
python3 -m healthpilot evidence-packet --profile <profile-name>
```

4. Treat `.state/profiles/{profile_slug}/evidence-packet.json` as an index, not sufficient evidence for high-impact conclusions.
5. Read `.state/profiles/{profile_slug}/issues.json`, `actions.json`, and cached SelfDecode genotypes when present, but verify important claims in canonical sources.
6. Inspect all relevant direct evidence:
   - scan `{labs_path}/all.csv` across all dates for abnormalities, trends, values needed by validated risk models, and cardiometabolic, renal, hepatic, hematologic, inflammatory, and nutritional modifiers
   - use `lab_specs.json` and source pages when units, ranges, or parser quality are ambiguous
   - inspect the complete standalone exam corpus layout, then retrieve diagnoses, pathology, imaging, endoscopy, sleep studies, screening, vital signs, anthropometrics, and surveillance findings
   - use `health_log.md`, relevant processed entries, and raw entries when exact timing or wording changes interpretation; retrieve smoking, alcohol, substance use, family history, medications, supplements, symptoms, infections, injuries, mental health, adherence, sleep, diet, activity, and longitudinal changes
   - read all configured lifestyle Markdown sources, using the personal context file as the conflict authority
   - use raw 23andMe and cached SelfDecode data through targeted extraction for well-replicated variants that could materially change a candidate cause; do not treat an uncurated genome-wide scan as clinically interpretable evidence
7. Record unavailable or stale sources and widen uncertainty. Shrink unsupported personalization toward the demographic baseline rather than assuming missing data means low risk.

“Use all data” means consider every available source and perform complete relevant retrieval; it does not mean assigning weight to irrelevant observations or treating every SNP as actionable.

## Population Baseline

Browse for the newest defensible baseline available at report time. Prefer, in order:

1. national vital-registration or official statistics matched by country, sex, and age
2. Eurostat or another official regional source with compatible strata
3. WHO Global Health Estimates matched by country or region, sex, age, and cause
4. a clearly labeled broader fallback when the required strata are unavailable

Use the underlying cause of death, not contributing conditions. Record the publisher, geography, population, data year, release date when available, age/sex stratum, cause taxonomy, and URL. Do not use a global top-10 list when a reliable matched national table exists.

Use age-specific life-table and cause-of-death data across future ages for a lifetime estimate when possible. Read [references/probability-method.md](references/probability-method.md) before estimating probabilities.

## Cause Taxonomy

Create mutually exclusive cause categories. Use an official ICD-based shortlist or a transparent mapping to one. Do not rank a parent and its child together; for example, do not include both `all cancer` and `colorectal cancer`, or both `cardiovascular disease` and `ischaemic heart disease`.

Prefer clinically interpretable underlying-cause categories. Treat hypertension, obesity, dyslipidemia, anemia, genetic variants, medications, and behaviors as risk modifiers rather than causes of death unless the official taxonomy defines a directly fatal category.

Include external causes such as unintentional injury or suicide only when they rank under the same evidence standard. Do not infer suicide risk from an ordinary mental-health mention. If the record contains current suicidal intent, a recent attempt, or an acute life-threatening symptom, interrupt the normal tone with an appropriate immediate safety note while still avoiding deterministic claims.

## Estimation Workflow

1. Build an age-, sex-, and geography-matched baseline over the selected horizon.
2. Start with enough mutually exclusive categories to preserve an `all other causes` residual after displaying the top 10.
3. Create a modifier ledger for each candidate cause:
   - observed profile evidence and date
   - direction of effect
   - magnitude or bounded multiplier when defensible
   - evidence source and applicability
   - counterevidence
   - uncertainty and correlation with other modifiers
4. Use a validated clinical risk model only when its population, age range, endpoint, horizon, and required inputs match this person. Name the version and cite it. Never fabricate a missing blood pressure, smoking status, cholesterol, diagnosis, or treatment value.
5. Do not present event-risk tools as mortality models. For example, a tool predicting fatal plus nonfatal cardiovascular events can inform a modifier, but it does not directly supply cardiovascular death probability.
6. Avoid double-counting correlated evidence such as BMI, insulin resistance, glucose, and diabetes, or a diagnosis plus the same lab values used to diagnose it.
7. Use conservative effect sizes, shrink weak or stale signals toward 1.0, and give small common genetic variants little weight unless replicated evidence and the person's phenotype support a larger effect.
8. Normalize across the full mutually exclusive cause set, not just the displayed top 10.
9. Rank the 10 highest point estimates. Add an unranked residual for every other cause. Ensure the 10 estimates plus the residual equal exactly 100%.
10. Give whole-number estimates by default and plausible ranges wide enough to reflect model and data uncertainty. Ranges need not sum to 100%.

When matched life-table inputs are available, use `scripts/estimate_competing_risks.py` to integrate cause-specific hazards and modifiers. Do not use that script with invented inputs. When the estimate is heuristic because full age-specific inputs are unavailable, say so prominently and do not call the output actuarial.

## Report Requirements

Use [references/report-template.md](references/report-template.md) as the starting structure.
Read [../_shared/healthpilot-report-contract.md](../_shared/healthpilot-report-contract.md) and apply it in full.

Start the decision layer with `## Principais riscos e medidas preventivas`. Show the leading risks, separate confidence and urgency, and identify the prevention action with the broadest cross-cause value before methodology or full ranking detail.

The ranked table must contain exactly 10 actual cause categories sorted by point estimate. Keep `all other causes` outside the ranking as the residual.

For each cause, include:

- point estimate and plausible range
- project confidence frame: render as `conclusão clara`, `diagnóstico provável`, `diagnóstico diferencial`, or `questão em aberto`; internal state may retain the canonical English enum
- matched population baseline
- observed supporting evidence with dates or source citations
- personalized inference and why it changes or preserves baseline rank
- contradicting or protective evidence
- missing data most likely to change the estimate
- strongest realistic prevention, screening, or risk-reduction action
- specialist type and specific discussion or test when appropriate

Apply the confidence frame to the present risk characterization, not to a certain future death. A future cause of death is never a `conclusão clara`; that label may apply only to an observed diagnosis or modifier.

Include cross-cause prevention priorities after the rankings. Prioritize actions that can reduce multiple leading risks, clarify a high-impact unknown, or change treatment. Do not pad the report with generic wellness advice or suggest prescription-only treatment without specialist evaluation.

## Calibration and Safety Rules

- State prominently that these are decision-support estimates, not clinically validated personalized predictions unless a named validated model directly produced the relevant number.
- Do not equate incidence with mortality, relative risk with absolute probability, or correlation with causation.
- Do not convert a genetic association into a diagnosis.
- Do not let one recent symptom or abnormal lab overwhelm age- and sex-specific competing risks without strong causal evidence.
- Do not imply that risk is fixed. Identify the most modifiable leading risks.
- Preserve sensitive details in the local report only; do not send or upload profile data to external services.
- Recommend specialist types only, never arbitrary named clinicians outside the record.

## Output Contract and Validation

Follow the common Healthpilot report convention:

- directory: `.output/{profile_slug}/mortality-risk/`
- filename: `{YYYY-MM-DD}-{profile_slug}-mortality-risk.md`
- canonical path: `.output/{profile_slug}/mortality-risk/{YYYY-MM-DD}-{profile_slug}-mortality-risk.md`

Use the local report date and canonical profile slug. If regenerating on the same date, refresh the canonical file instead of creating an alternate filename.

Validate the finished report:

```bash
python3 -m healthpilot validate-report \
  --type mortality-risk \
  --report .output/{profile_slug}/mortality-risk/{YYYY-MM-DD}-{profile_slug}-mortality-risk.md \
  [--previous .output/{profile_slug}/mortality-risk/{previous-filename}]

python3 .codex/skills/healthpilot-report-mortality-risk/scripts/validate_report.py \
  .output/{profile_slug}/mortality-risk/{YYYY-MM-DD}-{profile_slug}-mortality-risk.md
```

Fix every validator error before handing off the report. In the user-facing answer, link the report and summarize the probability definition, largest uncertainty, source gaps, and highest-leverage prevention priority.
