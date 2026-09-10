---
name: healthpilot-update-food-plan
description: Update a selected Healthpilot profile's food plan from personal constraints, recent health-log symptoms, representative Google Health trends and routine, and publish the latest one-page menu PDF at a stable path.
---

# Update food plan

Update the person's existing plan, not an unrelated ideal diet. A call to this skill authorizes the selected profile's context and food-plan updates and local PDF publication. It does not authorize changes to clinical sources, calendar events or another profile. Work from the Healthpilot repository root and follow its `AGENTS.md`.

## Canonical deliverables

- Personal guidance: selected live YAML's `data_sources.profile_context_md_path`.
- Current editable plan: `~/.config/healthpilot/profiles/{slug}.food-plan.md`, linked by `data_sources.nutrition_md_path`.
- Latest printable plan: `.output/{slug}/daily-plan/food-plan.pdf` (absolute path in the final response). Replace this stable file on successful updates; dates never enter its filename.
- Optional dated history is archival only. Keep the current Markdown coherent rather than accumulating contradictory revisions. Review timestamps and evidence-window dates support freshness; historical filenames are not required.

## Review the person and evidence

1. List live profiles with `ls ~/.config/healthpilot/profiles/*.yaml`. Use the named profile; ask which one only if ambiguous. Never fall back to repo example profiles. Parse YAML without displaying tokens or credentials. Read the **complete** personal context and current food plan; validate configured sources. If context is absent, resolve or bootstrap it from known user statements before personalizing. Bootstrap a missing plan only for the requested person.
2. Persist new user preferences, goals and constraints in context first. Retire conflicting old guidance. Attribute reports of fatigue, hunger, bloating, intolerance or poor energy as observations; do not invent diagnoses, allergies, measured weights or confirmed causal food triggers. Keep inferred proposals separate from user instructions.
3. Read recent `health_log.md` and relevant `entries/*.processed.md`, normally the latest 4–6 weeks; inspect raw entries where wording or timing matters. Look for energy, appetite, bowel symptoms, bloating, reflux, sleep, training, medication changes and actual adherence. Inspect older entries when needed to interpret an ongoing issue. Record the actual available period, not just the requested period. Review relevant labs/exams when they could change dietary advice; clinical/parser sources remain read-only.
4. Read [Google Health retrieval documentation](../../../docs/google-health.md). Inspect `healthpilot google-health-status --profile <slug>` privately. Retrieve **freshly on every invocation**, normally 28 completed source-calendar days ending yesterday, with:
   ```bash
   healthpilot google-health --profile <slug> --metrics calories weight steps sleep --start YYYY-MM-DD --end YYYY-MM-DD
   ```
   Use the local CLI environment (`uv run --frozen healthpilot ...` if needed). Add HRV/resting heart rate only when recovery questions justify them. Start with 28 days, compare the last 7 with the full window; extend to 6–8 weeks for sparse weights or atypical weeks when useful. Respect source dates, timezone, units and coverage. Weight arrives in grams: convert explicitly to kg. Latest seven dates refresh automatically; use `--refresh` for relevant historical corrections. Query success does not prove complete device wear.
5. Separate valid completed days from missing, stale, partial or implausible observations. Do not count missing values as zero, include today's partial calorie total, or silently delete genuine high-activity days. Summarize valid-day count, mean/median expenditure, recent change, steps/activity pattern, sleep and available weight trend. Explain exclusions and whether the window represents normal life. Total calories already include basal and activity expenditure: never add them again. Never borrow another profile's cache. If unavailable, continue with available evidence, explicitly retain a provisional target and describe the gap; do not claim expenditure-based calibration or start OAuth without owner consent.
6. Read `routine_calendar` through the available Google Calendar plugin when configured, covering a representative upcoming week and relevant exceptions. Calendar blocks are intentions, not measured activity. Fit meals and preparation around commitments without editing events. If access fails, preserve known timing as provisional and disclose stale coverage; do not invent free time or resurrect retired schedule-file sources.

## Adapt the plan

- Choose calories from the active goal, representative expenditure, actual intake if known, weight trajectory, symptoms and activity. Wearable expenditure is an estimate, not measured maintenance. Compare 2–3 weeks of weight averages when available. If weights/adherence are absent, avoid a precise deficit claim. Prefer modest adjustments with a clear rationale over chasing day-to-day calorie changes; unchanged intake is a valid outcome.
- Do not automatically cut food for fatigue, low HRV or stalled weight. Consider sleep, illness, medication, training and under-fuelling; flag a material clinical concern separately rather than implying a menu fixes it. Research current authoritative guidance when introducing clinical recommendations or a new deficit/protein target. Respect condition-specific constraints.
- Preserve familiar meals, meal timing, food preferences and practical portion conventions. Inherit the profile's language. Use raw edible weights/dry grains where preferred; keep ready-made foods as sold and soup as prepared volume unless its recipe is known. Recalculate from matching raw/cooked nutrition references rather than applying an exact universal yield factor.
- Use label calories for specified products; otherwise document the reference and assumption. Household spoons/handfuls and mixed-fruit/nut estimates need a gram anchor and approximate calories. Do not imply all nuts or arbitrary container fillings are interchangeable. Check context-specific restrictions (including high-selenium Brazil nuts, when relevant) before generic mixtures. Do not invent supplement doses or assign unquantified ingredients zero calories.
- Respect lunch/dinner protein preferences and container capacity. If fit is uncertain, state that in the Markdown; grams are not millilitres. Keep soup/fruit separate where specified. Do not silently reduce vegetables/protein just to fill a box.
- Reconcile the **actual menu sum** with the intended target. If edits increase it materially, adjust suitable portions consistent with constraints or explicitly explain the unresolved difference; never label a higher summed menu as the old target. Explain changes and assumptions in the canonical Markdown, including evidence coverage, source references, review date and what would prompt the next adjustment. Keep obsolete instructions out of current sections; an optional short history can retain prior versions.

## Produce and verify the PDF

Use the available PDF skill for its authoring marker and visual-verification requirements, and bundled workspace dependencies for ReportLab/pypdf. Read [the rendering contract](references/pdf-contract.md). The included renderer removes repeated hand-written table code; it does **not** make nutrition decisions.

1. Finish the coherent current Markdown menu and rationale. Create a local JSON rendering spec from its exact quantities and calories. Keep private specs under `.output/{slug}/daily-plan/assets/` or ignored scratch, never tracked skill assets.
2. Render to a candidate file under `.output/{slug}/daily-plan/`, not directly over the last good PDF:
   ```bash
   python .codex/skills/healthpilot-update-food-plan/scripts/render_food_plan.py --spec <local-spec.json> --output <candidate.pdf>
   ```
3. Verify item values match Markdown, meal sums and daily sum, raw/cooked labels, unknown calories and preference compliance. Render the candidate with `pdftoppm` and inspect the whole page. No clipped cells, overlapping text, tiny text or extra pages. If it will not fit, shorten wording; do not drop food or hide uncertainty to force one page.
4. After validation, atomically replace `.output/{slug}/daily-plan/food-plan.pdf` with the candidate on the same filesystem (e.g. `os.replace`). A failed render must leave the existing latest PDF intact. Optional archives must not replace the stable entry point. Record the stable absolute PDF path in the canonical food-plan Markdown for discovery.
5. Return the stable PDF path/link using the PDF skill's output citation, with a brief explanation of material changes, approximate calorie total and material unavailable evidence. The PDF itself contains food, portions, item calories, meal subtotals and total only, plus concise measurement/estimate notes. Put medical reasoning and source coverage in Markdown, not the printable menu.
