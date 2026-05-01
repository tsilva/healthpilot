---
name: root-cause-analysis
description: Generate a dated root-cause differential report for a selected live healthpilot profile. Use when the user asks for the most likely causes of a symptom, condition, abnormal marker, episode, pattern, or health problem, especially when they want top-K hypotheses with explicit probabilities that add to 100% and explanations for each probability.
---

# Root Cause Analysis

Use this skill when the user asks "what is causing X?", "find the root cause of X", "rank likely causes", or wants a probability-weighted differential for a symptom, condition, abnormal lab, episode, recurring pattern, or unresolved health problem.

The deliverable is a dated Markdown report under `.output/` containing the top K hypotheses, sorted by probability, with probabilities adding exactly to 100%.

## Required Session Rules

1. Follow the profile and source-validation rules from `AGENTS.md`.
2. Treat profile-linked external sources as read-only.
3. Write the user-facing report under `.output/{profile_slug}/`.
4. Use `.state/` only as optional memory; do not require it.
5. Distinguish observed evidence from inference.

## Inputs

- `query`: the symptom, condition, marker, episode, or pattern to explain.
- `K`: number of hypotheses to return. If the user does not specify K, default to 5.

If the query is ambiguous, make the narrowest reasonable interpretation from context and state it in the report. Ask a clarifying question only if a reasonable interpretation would be unsafe or likely useless.

## Retrieval Order

Use the shortest path that can defensibly cover all relevant data types.

1. Load the selected live profile and classify every configured source as `available`, `missing`, `unreadable`, or `not configured`.
2. Generate or read the current evidence packet when available:

```bash
healthpilot evidence-packet --profile <profile-name>
python3 -m healthpilot evidence-packet --profile <profile-name>
```

3. Use `.state/profiles/{profile_slug}/evidence-packet.json` as a factual map, not as final reasoning.
4. Search the health log for the query and close synonyms:
   - `{health_log_path}/health_log.md`
   - recent and relevant `entries/*.processed.md`
   - `entries/*.raw.md` only when exact wording, timing, severity, triggers, or medication response matters
5. Search labs:
   - start with `{labs_path}/all.csv`
   - use `{labs_path}/lab_specs.json` for marker naming, units, and ranges when present
   - inspect dated folders only for source verification or ambiguous OCR/parser details
6. Search standalone exams first for imaging, endoscopy, procedure, sleep-study, pathology, or specialist-test evidence.
7. Use genetics only when it could materially change the ranked hypotheses or medication/treatment-path interpretation. For SelfDecode SNPs, check `.state/profiles/{profile_slug}/selfdecode-genotypes.json` first, then use the cache-aware helper only for missing rsIDs:

```bash
python3 -m healthpilot selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
SELFDECODE_JWT="<token>" python3 -m healthpilot selfdecode-genotypes --profile <profile-name> --rsids rs123 rs456
```

If authentication is needed, tell the user to copy the `token` field from the `/service/health-analysis/accounts/user/token/` Network response on a logged-in SelfDecode SNP page. Do not ask for the OpenID/Auth0 authorization header. Never store JWTs; the helper caches genotypes only.
8. Use lifestyle Markdown sources when schedule, food, exercise, sleep, recovery, triggers, or constraints could explain the query.
9. If a configured source is unavailable, say so in the report and reduce confidence accordingly.

## Hypothesis Rules

Rank candidate root causes as conditions, mechanisms, or clinically meaningful explanatory buckets. Prefer specific, testable hypotheses over vague labels.

Each hypothesis must include:

- `probability`: integer or one-decimal percentage
- `confidence frame`: `clear conclusion`, `likely diagnosis`, `differential`, or `open question`
- `why this probability`: explanation for the assigned probability
- `supporting evidence`: observed evidence with dates or source references when possible
- `contradicting / weakening evidence`: evidence against it or reasons it is less likely
- `missing data that would change probability`
- `next best test or action`
- `specialist type` when a specialist path is appropriate

Use `clear conclusion` only when the record directly proves the cause. Most root-cause reports should use `likely diagnosis`, `differential`, and `open question`.

## Probability Rules

The report must contain exactly K ranked rows unless the available evidence cannot support K meaningful hypotheses without padding. If fewer than K are reported, state why.

Probabilities must:

- be sorted from highest to lowest
- add to exactly `100%`
- be evidence-weighted working probabilities, not definitive diagnoses
- reflect the current profile record, not population prevalence alone
- be recalibrated downward when key sources are missing, sparse, old, contradictory, or ambiguous

Include an `Other / insufficiently captured by available record` bucket when the evidence strongly suggests meaningful residual uncertainty. Count that bucket toward K.

Prefer calibrated ranges internally, then choose a point estimate for the table. The written explanation must justify why the final point estimate is higher or lower than the alternatives.

Do not use false precision. Use whole percentages unless one decimal place is genuinely helpful for a close tie.

## Report Structure

Use [references/report-template.md](references/report-template.md) as the starting structure.

The report should include:

1. Title
2. `Report generated`
3. `Profile`
4. `Query interpreted as`
5. `Source status`
6. `Probability summary`
7. `Ranked root-cause assessment`
8. `Most important uncertainty`
9. `Next best actions`
10. `What to return with`

## Output Filename

Write the report to:

`{profile_slug}/{YYYY-MM-DD}-{profile_slug}-root-cause-{query_slug}.md`

Keep `query_slug` short, lowercase, and filesystem-safe.

## Reasoning Standard

Do not stop at "talk to a doctor." For each high-probability or high-impact hypothesis, identify the specialist type and the specific test, treatment discussion, or observation that would most change the probability.

For safety-critical symptoms or red flags found in the record, include an urgent-care note in `Next best actions`, but keep the main report focused on root-cause ranking.

Avoid generic root-cause lists. Every listed hypothesis should have a reason it belongs in this specific profile's record.
