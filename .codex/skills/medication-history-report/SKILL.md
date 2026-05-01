---
name: medication-history-report
description: Generate a dated Markdown report of active medications, past medications, and supplements from a selected live healthpilot profile. Use when the user asks for a medication list, supplement list, medication history, or a written medication/supplement report in .output/.
---

# Medication History Report

Generate a repo-local Markdown report for the selected live profile.

## Inputs

- Follow the session-start rules in `AGENTS.md`.
- Use the selected live profile under `~/.config/healthpilot/profiles/`.
- Treat external data sources as read-only.

## Retrieval Order

1. Validate configured sources and record each as `available`, `missing`, `unreadable`, or `not configured`.
2. Use `{health_log_path}/health_log.md` as the primary medication/supplement source.
3. Use `entries/*.processed.md` and `entries/*.raw.md` to confirm recent starts, stops, and dosage details.
4. Use `entries/*.exams.md` or the standalone exams corpus only when a prescription or dose needs confirmation.

## Classification Rules

- Prefer the latest explicit current-state statement over older notes.
- Mark an item `active` only when the latest evidence supports ongoing use.
- If later notes show use but do not clearly confirm continuation through the latest record, put the item under `open question` rather than `active`.
- Put short courses, one-off symptom treatments, and experiments under `past/intermittent`.
- Deduplicate synonyms such as `PPI` and `Pantoprazole` when they clearly refer to the same item.
- For active medications and active supplements, include dosage and schedule when recorded. If the item is active but the dose is unclear, write `dose not recorded`.

## Output

Write the report under `.output/` using a filename shaped like:

`{profile_slug}-medication-history-{YYYY-MM-DD}.md`

The report must include the generation date inside the file near the top:

`Report generated: YYYY-MM-DD`

If a time is readily available, prefer:

`Report generated: YYYY-MM-DD HH:MM TZ`

## Report Structure

Use this section order:

1. Title
2. `Report generated`
3. `Profile`
4. `Source status`
5. `Clear conclusion`
6. `Open question`
7. `Active medications`
8. `Active supplements`
9. `Past/intermittent medications`
10. `Past/intermittent supplements`
11. `Evidence notes`

Keep each item concise. For each medication or supplement, include:

- name
- dose and schedule when known
- status classification
- a short evidence note with the most relevant date(s)

## Template

Use [references/report-template.md](references/report-template.md) as the starting structure, then fill it with profile-specific content.
