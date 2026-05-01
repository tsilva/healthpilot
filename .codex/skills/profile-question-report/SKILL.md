---
name: profile-question-report
description: Ask a selected live healthpilot profile's 10 highest-yield unanswered questions interactively, then write a paste-ready Markdown health-log entry under .output/ for the user's real health log.
---

# Profile Health-Log Interview

Run an interactive interview for the selected live profile, then generate a paste-ready health-log entry.

Use this when the user wants the agent to ask profile-specific questions and turn the answers into a health-log entry that will help future runs reason better.

## Required Session Rules

1. Follow the session-start and source-validation rules in `AGENTS.md`.
2. Treat all profile-linked external sources as read-only.
3. Write the user-facing health-log entry draft under `.output/`.
4. Do not create new `.state/` artifacts for this workflow.
5. Never write into the configured external `health_log_path`.

## Goal

Ask the highest-yield unanswered questions for that profile, then transform the user's answers into a concise Markdown health-log entry draft.

The questions should help the next run by clarifying:

- diagnosis ranking
- treatment-path recommendations
- specialist direction
- important chronology or response-pattern gaps that materially change interpretation

Do not pad the report with broad intake questions, generic wellness prompts, or low-value curiosity items.

## Retrieval Order

1. Read the selected live profile and classify each configured source as `available`, `missing`, `unreadable`, or `not configured`.
2. Check repo-local memory first when available:
   - `.state/profiles/{profile_slug}/issues.json` for unresolved issue gaps
   - `.state/profiles/{profile_slug}/actions.json` only as supporting context
3. Use the latest health-log context next:
   - `{health_log_path}/health_log.md`
   - recent `entries/*.processed.md`
   - recent `entries/*.raw.md` only when exact wording matters
4. Pull labs, standalone exams, and genetics only as needed to confirm whether a question is already answered or still materially open.
5. Prefer the shortest path that can prove a question is still worth asking.

## Question Selection Rules

Select exactly 10 questions when the available evidence supports 10 meaningful questions.

Ask fewer than 10 only when the record cannot support 10 high-yield questions without padding. If asking fewer, state the reason briefly in the generated entry's metadata section.

Include questions only when the answer would likely change future recommendations in a meaningful way.

Prefer questions that would:

- narrow a real differential
- clarify whether a symptom pattern is episodic, persistent, or triggered
- distinguish medication or supplement benefit vs side effect
- clarify whether prior testing or specialist guidance already happened
- identify missing objective data that would change the next step

Exclude questions that are already clearly answered in the record, including cases where the answer appears repeatedly across sources.

Also exclude:

- vague prompts like "How is your lifestyle?"
- generic optimization questions with no record support
- exhaustive history-taking that is unlikely to change the plan now

## Ranking Rules

Rank questions in this order:

1. answers that could materially change diagnosis ranking
2. answers that could change treatment class or specialist path
3. answers that resolve a key missing objective-evidence gap
4. answers that clarify whether a concerning issue is still active
5. foundational context questions for sparse records

## Interactive Interview Rules

Prefer the structured question tool when it is available.

Use batches of at most 3 questions:

1. Ask questions 1-3.
2. Ask questions 4-6.
3. Ask questions 7-9.
4. Ask question 10.

For each question-tool prompt:

- Use a stable `snake_case` answer id.
- Keep the header 12 characters or shorter.
- Provide 2-3 short mutually exclusive options, usually `Yes`, `No`, and `Unsure` or equivalent context-specific choices.
- In the prompt text, tell the user to use the free-form `Other` answer when they can provide details, dates, severity, medication names, test names, or specialist guidance.
- Do not include an `Other` option manually if the tool adds it automatically.

After each batch, preserve the user's answers verbatim enough to avoid losing dates, qualifiers, and uncertainty.

If the question tool is unavailable, ask the ranked questions as a numbered chat list and wait for the user's answers before writing the entry. The fallback output must match the normal `.output/` entry format.

## Health-Log Entry Drafting Rules

Write in first person as a paste-ready health-log entry from the user's perspective.

Preserve uncertainty clearly. Use wording like:

- "I am unsure whether..."
- "I do not remember..."
- "I have not answered..."

Do not invent answers, dates, severity, medications, test results, specialist advice, or symptom patterns.

Group related answers by topic when it improves readability. Keep the entry concise and free of agent-facing explanation inside the paste-ready entry body.

Include a short `Not answered / still unclear` section only when the user skipped questions, gave ambiguous answers, or chose `Unsure`.

## Output

Write the health-log entry draft under `.output/` using this filename:

`{profile_slug}/{YYYY-MM-DD}-{profile_slug}-health-log-entry.md`

Use [references/report-template.md](references/report-template.md) as the starting structure.

## Output Rules

- Include the profile name and source status.
- If a source is unavailable, say so explicitly and adjust the questions to that narrower evidence base.
- Include the generated paste-ready health-log entry.
- Keep the question list out of the final output unless a short "Questions asked" appendix is needed to clarify skipped or uncertain answers.
- Do not create a standalone unanswered-question report.
