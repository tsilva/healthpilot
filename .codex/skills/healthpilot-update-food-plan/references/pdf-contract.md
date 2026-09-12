# Menu and optional swap-page contract

Use A4 portrait, the established pale-green meal bands and a three-column grid: food, quantity/weight state, approximate kcal. Preserve the selected profile's language; no imposed count of meals or specific foods. Show a fixed menu without alternatives unless that profile requests them. Put cheese eaten after dinner in that meal's rows; keep similar practical ordering from the current plan.

The renderer takes a JSON object:

```json
{
  "title": "Food plan",
  "note": "Weigh cooked foods ready to eat; packaged foods as sold.",
  "columns": ["Food", "Quantity / weight state", "kcal ≈"],
  "total_label": "FOOD TOTAL",
  "total_note": "Excludes ingredients with unknown calories",
  "unknown_label": "Unknown",
  "footer": "Calories are estimates; unknown items are additional.",
  "meals": [
    {"name": "Breakfast", "items": [
      {"food": "Cooked rice", "quantity": "100 g cooked, without added fat", "kcal": 130}
    ]}
  ],
  "unquantified": [
    {"food": "User-reported ingredient", "quantity": "Amount/label not yet confirmed", "kcal": null}
  ]
}
```

When the selected profile requests a second page, add an optional `swaps` object with `title`, `sections`, an optional `intro`, and optional `notes` (a list of short plain-text paragraphs). Omit the introduction and notes when the profile requests a tables-only page. Each section contains `title`, `columns`, `widths` (points, positive and totaling 515), and nonempty `rows` of plain-text cells matching the column count. Put the exchange basis, cooked state, reference portions, calories/protein and necessary exclusions in this page. Omit `swaps` to retain the one-page output. The renderer rejects an overflowing second page and publishes only after the expected page count is verified. Nutrition calculations remain the agent's responsibility.

`meals` is nonempty; each meal has a name and nonempty items. Use integer, nonnegative item calories rounded from nutrition calculations. Totals are computed, not supplied. Unknown-calorie items belong in `unquantified` and must explicitly have `kcal: null`; the PDF must clearly say they are excluded from the numeric total. Omit this list when everything is quantified. Do not copy the illustrative unknown ingredient into real menus.

All strings are plain text, not ReportLab markup. The renderer escapes them. Measurement qualifiers belong in `quantity`; labels and notes can be localized. Keep the header note and footer concise (one line each). The renderer checks cell height, page bounds and the requested one- or two-page output before publishing its requested file. It cannot verify clinical suitability, nutrition references, source freshness or that a JSON spec matches the Markdown; the agent must check those.

Run with the bundled Python containing ReportLab and pypdf. No dependency installation or project dependency change is required. Create a candidate, visually inspect it, then replace the canonical PDF only on success.
