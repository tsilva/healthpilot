# Google Health wearable evidence

Google Health is an optional source for existing local runtime profiles. The agent remains the report interface: ask for the relevant wearable trend, episode, or report, with a profile and date window. The commands below support that workflow and ad hoc retrieval. No runtime profile YAML change is needed.

## Connect a profile

1. Follow [Google Health Cloud/OAuth setup](https://developers.google.com/health/setup) to enable the **Google Health API** in one Google Cloud project and configure its consent screen. This integration uses `health.googleapis.com/v4`, not Cloud Healthcare, Google Fit, or the legacy Fitbit Web API.
2. Create an OAuth client of type **Desktop app**, and download its client JSON outside the repository. For an external app in Testing, add each account owner as a test user. Use this same application for every local profile.
3. Add these read scopes to the consent screen's Data Access configuration:
   - `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
   - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
   - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
4. Import the shared client, then authorize each selected profile. Replace the sample values with the existing profile slug and that person's Google email. `--timezone` is an IANA timezone for the current-day refresh policy; it defaults to UTC if omitted.

```bash
healthpilot google-health-configure --client-file ~/Downloads/google-desktop-client.json
healthpilot google-health-connect --profile myname --account person@example.com --timezone Europe/Lisbon
healthpilot google-health-status --profile myname
```

Connection opens the system browser and listens briefly on an ephemeral `127.0.0.1` port. It uses OAuth state and PKCE, requests offline access, and verifies both the expected email through Google's authenticated OpenID userinfo endpoint and the Google Health user identity. The identity scopes are `openid` and `email`; all health scopes are read-only. Grant the three health read permissions to retrieve all supported metrics. Missing permissions remain visible by metric.

`google-health-status` displays the linked account, timezone, and granted/missing scopes locally. It does not make network requests or certify that authorization is still valid. Access tokens renew only when retrieval needs a network request. If Google revokes or expires authorization, reconnect with the same command. **Testing-mode refresh tokens expire after seven days**; this is a Google OAuth rule, independent of the seven-day measurement refresh policy. See [Google OAuth expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

Reconnection must match the existing account binding. To correct a profile that was connected to the wrong person, first remove that profile's entire `google-health/profiles/<slug>/` runtime directory (credentials **and** cache), then reconnect. This discards that profile's downloaded wearable history, which can be fetched again. Revoking access in the Google account is separate from deleting local credentials.

## Retrieve evidence

Both boundary dates are inclusive **source civil calendar dates**. Physical timestamps, UTC offsets, daily dates, and source units remain in each record. Sleep is assigned to its waking/end date, matching the API's supported filter. The connection timezone defines “today” for refresh decisions; it does not reinterpret source timestamps or historical travel offsets.

```bash
healthpilot google-health --profile myname --metrics hrv resting-heart-rate weight sleep steps calories --start 2026-08-01 --end 2026-08-31
healthpilot google-health --profile myname --metrics heart-rate --start 2026-08-15 --end 2026-08-15
healthpilot google-health --profile myname --metrics hrv --start 2026-01-01 --end 2026-01-31 --refresh
```

| Metric | Google Health data type / retrieval | Source units |
| --- | --- | --- |
| `hrv` | `daily-heart-rate-variability`, reconcile | HRV milliseconds; optional non-REM bpm and entropy remain distinct |
| `resting-heart-rate` | `daily-resting-heart-rate`, reconcile | beats/minute |
| `heart-rate` | `heart-rate`, reconcile | beats/minute, individual sample timestamps |
| `weight` | `weight`, reconcile | grams |
| `sleep` | `sleep`, reconcile | summary durations in minutes; session and stage timestamps |
| `steps` | `steps`, dailyRollUp | step count |
| `calories` | `total-calories`, dailyRollUp | `kcalSum`, estimated total kilocalories |

The integration asks Google to reconcile **all sources** into a single stream. Device provenance is therefore the reconciled Google Health stream; it must not be attributed to a specific device unless independently supported. It retains a hash of the source record identifier where provided. Total calories already include the components of total expenditure: do not add activity or basal energy, or separate device totals, to them. Calorie expenditure is an estimate, and wearable observations alone do not establish diagnoses.

Low-volume daily/weight/step requests can fill the surrounding calendar month. Sleep requests may fill up to seven days from a missing date; calorie requests up to fourteen. Extra dates already covered are reused. Detailed heart rate is fetched in one-day chunks. Pages are followed sequentially (reconcile maximum 10,000 records; sleep maximum 25). Daily rollups use Google's default page size: live verification on 2026-09-09 found that explicitly requesting 10,000 returns HTTP 400 despite the reference limit. The calorie rollup never exceeds the documented fourteen-day range. These windows are application choices within the [verified API limits](https://developers.google.com/health/endpoints); no whole-year detailed download is implicit.

The latest seven calendar days (today and the preceding six), when requested, are fetched again on every retrieval. Older successful coverage, including empty results, is reused. `--refresh` refreshes the explicitly requested historical range. Older corrections are otherwise not guaranteed to appear. A current day or a successful empty response does not prove complete device wear or synchronization.

Each metric returns measurements, `coverage` with retrieval timestamps, `missing_days`, `stale_days`, `empty_days`, and safe error categories. `complete` means the requested query pages were retrieved successfully; it does not mean the device measured continuously. A failed or malformed page never advances that window's coverage. Previously complete records survive as stale evidence, and missing windows remain partial. Transient errors use bounded retries. A failed window stops further windows for that metric in the current request; other metrics still run. A later request retries gaps.

## Reports and source validation

Choose a clinically relevant metric/date window before interpreting wearable evidence. Reports can retrieve it during the normal deterministic refresh:

```bash
healthpilot plan --profile myname --wearable-metrics hrv resting-heart-rate sleep --wearable-start 2026-08-01 --wearable-end 2026-08-31
healthpilot evidence-packet --profile myname --wearable-metrics heart-rate --wearable-start 2026-08-15 --wearable-end 2026-08-15
```

The same optional flags work with `daily-plan`; `--wearable-refresh` requests historical correction retrieval. Supply all three selection flags together. Ordinary runs without these flags use the **last selected wearable request** from the profile's cache without network access. They do not imply coverage for other dates or metrics. Cached recent dates become stale on a later calendar day; for a fresh report, explicitly retrieve its relevant window to catch same-day delayed syncs as well.

Source snapshots expose `google_health` availability and metric coverage without a credential directory path. The v2 evidence packet adds `wearables` and `[WEARABLE:…]` entries to its citation index. Its snapshot identity includes wearable coverage changes. Unconnected profiles continue to work and report this source as `not configured`; a connected profile without a selected cached window reports `missing`. Partial, stale, permission-denied, reconnect-required, and unreadable states are explicit. Use those limitations in the report's evidence appendix. Never interpret missing data as reassuring findings, and never copy account identity or runtime paths into a report.

## Runtime storage and verification

Everything belonging to the connection lives under `~/.config/healthpilot/google-health/`:

```text
application.json                     shared Desktop client configuration
profiles/<canonical-slug>/
  credentials.json                   account binding, access/refresh tokens, scopes, timezone
  measurements.sqlite3               transactional per-metric/day cache and identity binding
  last-request.json                  last selected date/metric window and binding
  .lock                              local serialization of connection/cache updates
```

Credentials and caches are separated by canonical profile slug and verified account identity. There is no cross-profile fallback. Runtime directories use mode 0700 and credential files 0600, with atomic replacement. Generated reports and deterministic source state keep their existing `.output/` and `.state/` locations; profile-linked source inputs remain read-only. Do not place downloaded OAuth client JSON, tokens, or the runtime directory in Git.

Run the synthetic command-boundary tests with the locked dev environment:

```bash
uv sync --frozen --extra dev
uv run --frozen python -m pytest tests/test_google_health.py
```

This feature introduces no new dependencies. The automated tests substitute Google's transport and browser authorization while exercising the real CLI, loopback callback, profile binding, cache, and evidence packet. No real account or live health data is required. After the account owner explicitly authorizes, a live smoke check should retrieve a small window for each relevant metric and inspect actual availability and units. Some metrics can be absent for the account/device. No live account connection is created by the test suite.

API references checked during implementation: [reconcile](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/reconcile), [filters and scopes](https://developers.google.com/health/filters), [dailyRollUp](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/dailyRollUp), [identity](https://developers.google.com/health/reference/rest/v4/users/getIdentity), and [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app).
