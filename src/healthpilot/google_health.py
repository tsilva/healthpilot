"""Profile-scoped, on-demand Google Health evidence, in source civil calendar days."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from healthpilot.evidence_hygiene import evidence_reference
from healthpilot.google_health_auth import (
    API, HEALTH_SCOPES, AuthorizedClient, GoogleHealthError, credentials, profile_directory,
    profile_lock, read_private, write_private,
)
from healthpilot.google_health_cache import CoverageCache
from healthpilot.profile import ProfileContext


@dataclass(frozen=True)
class Metric:
    data_type: str
    field: str
    time_field: str
    scope: str
    window_days: int
    units: str
    rollup: bool = False


METRICS = {
    "hrv": Metric("daily-heart-rate-variability", "dailyHeartRateVariability", "date", HEALTH_SCOPES[0], 31, "HRV: milliseconds; non-REM heart rate: beats/minute; entropy: dimensionless"),
    "resting-heart-rate": Metric("daily-resting-heart-rate", "dailyRestingHeartRate", "date", HEALTH_SCOPES[0], 31, "beats/minute"),
    "heart-rate": Metric("heart-rate", "heartRate", "sample_time.civil_time", HEALTH_SCOPES[0], 1, "beats/minute"),
    "weight": Metric("weight", "weight", "sample_time.civil_time", HEALTH_SCOPES[0], 31, "grams"),
    "sleep": Metric("sleep", "sleep", "interval.civil_end_time", HEALTH_SCOPES[2], 7, "summary durations: minutes; source timestamps retained"),
    "steps": Metric("steps", "steps", "", HEALTH_SCOPES[1], 31, "count", True),
    "calories": Metric("total-calories", "totalCalories", "", HEALTH_SCOPES[1], 14, "kilocalories (estimated total expenditure)", True),
}
DEFAULT_METRICS = tuple(name for name in METRICS if name != "heart-rate")


def calendar_days(start: date, end: date) -> list[str]:
    if start > end:
        raise GoogleHealthError("unavailable", "Start date must not be after end date.")
    return [(start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)]


def _date_object(value: date) -> dict[str, int]:
    return {"year": value.year, "month": value.month, "day": value.day}


def _civil_day(value: Any) -> str:
    if isinstance(value, str):
        return date.fromisoformat(value[:10]).isoformat()
    return date(int(value["year"]), int(value["month"]), int(value["day"])).isoformat()


def _record_day(data: dict[str, Any], metric: Metric, row: dict[str, Any]) -> str:
    if metric.rollup:
        return _civil_day(row["civilStartTime"]["date"])
    if metric.time_field == "date":
        return _civil_day(data["date"])
    if "sampleTime" in data:
        timing = data["sampleTime"]
        civil, physical, offset = "civilTime", "physicalTime", "utcOffset"
    else:
        timing = data["interval"]
        civil, physical, offset = "civilEndTime", "endTime", "endUtcOffset"
    if civil in timing:
        value = timing[civil]
        return _civil_day(value["date"] if isinstance(value, dict) else value)
    timestamp = datetime.fromisoformat(timing[physical].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or not timing[offset].endswith("s"):
        raise ValueError("Missing source timezone")
    return (timestamp.astimezone(timezone.utc) + timedelta(seconds=float(timing[offset][:-1]))).date().isoformat()


def _normalize(row: dict[str, Any], name: str, metric: Metric) -> dict[str, Any] | None:
    data = row.get(metric.field)
    # A rollup with no value means no measurements, not zero.
    if data is None and metric.rollup:
        return None
    if not isinstance(data, dict):
        raise ValueError("Missing data payload")
    day = _record_day(data, metric, row)
    payload = dict(data)
    if metric.rollup:
        payload["civilStartTime"] = row["civilStartTime"]
        payload["civilEndTime"] = row["civilEndTime"]
    anchor = payload.get("date") or payload.get("sampleTime") or payload.get("interval") or row.get("civilStartTime")
    identifier = hashlib.sha256(json.dumps([name, anchor], sort_keys=True).encode()).hexdigest()[:20]
    return {"id": identifier, "observed_at": day, "data": payload,
            "units": metric.units, "source_type": "google_health",
            "provenance": {"provider": "Google Health v4", "method": "dailyRollUp" if metric.rollup else "reconcile",
                           "data_source_family": "all-sources",
                           "source_record_hash": hashlib.sha256(str(row.get("dataPointName", "")).encode()).hexdigest() if row.get("dataPointName") else ""},
            "citation_id": evidence_reference("wearable", observed_at=day, label=f"{name}-{identifier}"),
            "citation_label": f"Google Health {name}, {day}"}


def _fetch(client: AuthorizedClient, name: str, start: date, end: date) -> dict[str, list[dict[str, Any]]]:
    metric = METRICS[name]
    url = f"{API}/users/me/dataTypes/{metric.data_type}/dataPoints"
    days: dict[str, dict[str, dict[str, Any]]] = {day: {} for day in calendar_days(start, end)}
    page_token = ""
    seen_tokens: set[str] = set()
    while True:
        if metric.rollup:
            params = {"range": {"start": {"date": _date_object(start)},
                                 "end": {"date": _date_object(end + timedelta(days=1))}},
                      "windowSizeDays": 1, "pageSize": 10000,
                      "dataSourceFamily": "users/me/dataSourceFamilies/all-sources"}
            if page_token:
                params["pageToken"] = page_token
            response = client.request(url + ":dailyRollUp", scope=metric.scope, body=params)
            rows = response.get("rollupDataPoints", [])
        else:
            field = metric.data_type.replace("-", "_") + "." + metric.time_field
            params = {"filter": f'{field} >= "{start}" AND {field} < "{end + timedelta(days=1)}"',
                      "pageSize": 25 if name == "sleep" else 10000,
                      "dataSourceFamily": "users/me/dataSourceFamilies/all-sources"}
            if page_token:
                params["pageToken"] = page_token
            response = client.request(url + ":reconcile?" + urllib.parse.urlencode(params), scope=metric.scope)
            rows = response.get("dataPoints", [])
        try:
            if not isinstance(rows, list):
                raise ValueError
            for row in rows:
                record = _normalize(row, name, metric)
                if record is None:
                    continue
                if record["observed_at"] not in days:
                    raise ValueError("Out of range data")
                days[record["observed_at"]][record["id"]] = record
            next_token = response.get("nextPageToken", "")
            if not isinstance(next_token, str) or (next_token and next_token in seen_tokens):
                raise ValueError("Invalid pagination")
        except (KeyError, ValueError, TypeError, AttributeError):
            raise GoogleHealthError("partial", "Google Health returned incomplete or invalid measurements; coverage was not advanced.") from None
        if not next_token:
            return {day: list(records.values()) for day, records in days.items()}
        seen_tokens.add(next_token)
        page_token = next_token


def _windows(start: date, end: date, metric: Metric, cached: dict[str, Any], today: date,
             refresh: bool) -> list[tuple[date, date]]:
    requested = calendar_days(start, end)
    recent = (today - timedelta(days=6)).isoformat()
    needed = {day for day in requested if refresh or day >= recent or not cached.get(day, {}).get("fetched_at") or cached.get(day, {}).get("error")}
    if not refresh:
        # Broaden only newly missing history. Never refetch known history as a side effect.
        for day in list(needed):
            if cached.get(day, {}).get("fetched_at"):
                continue
            target = date.fromisoformat(day)
            base = target.replace(day=1) if metric.window_days == 31 else target
            limit = (base.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1) if metric.window_days == 31 else base + timedelta(days=metric.window_days - 1)
            for candidate in calendar_days(base, min(limit, today)):
                if not cached.get(candidate, {}).get("fetched_at"):
                    needed.add(candidate)
    windows: list[tuple[date, date]] = []
    for day in sorted(needed):
        value = date.fromisoformat(day)
        if windows and value == windows[-1][1] + timedelta(days=1) and (value - windows[-1][0]).days < metric.window_days:
            windows[-1] = (windows[-1][0], value)
        else:
            windows.append((value, value))
    return windows


def _evidence(name: str, days: list[str], cached: dict[str, Any], today: date,
              checked_at: str, *, offline: bool = False,
              clock_zone: ZoneInfo | timezone = timezone.utc) -> dict[str, Any]:
    missing = [day for day in days if not cached.get(day, {}).get("fetched_at")]
    stale = [day for day in days if cached.get(day, {}).get("fetched_at") and (
        cached[day].get("error") or (offline and day >= (today - timedelta(days=6)).isoformat()
        and datetime.fromisoformat(cached[day]["fetched_at"]).astimezone(clock_zone).date() < today))]
    records = [record for day in days for record in cached.get(day, {}).get("records", [])]
    errors = sorted({cached[day]["error"] for day in days if cached.get(day, {}).get("error")})
    return {"status": "partial" if missing else "stale" if stale else "complete",
            "records": records, "missing_days": missing, "stale_days": stale,
            "empty_days": [day for day in days if cached.get(day, {}).get("fetched_at") and not cached[day]["records"]],
            "coverage": {day: {"fetched_at": cached[day]["fetched_at"], "error": cached[day]["error"]}
                         for day in days if day in cached}, "errors": errors,
            "units": METRICS[name].units, "checked_at": checked_at}


def retrieve(*, profile: ProfileContext, home_dir: Path, start: date, end: date,
             metrics: list[str], refresh: bool = False, offline: bool = False) -> dict[str, Any]:
    if any(metric not in METRICS for metric in metrics):
        raise GoogleHealthError("unavailable", "Unsupported metric; choose: " + ", ".join(METRICS))
    days = calendar_days(start, end)
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date()
    result: dict[str, Any] = {"source_type": "google_health", "profile_slug": profile.slug,
        "status": "not configured", "start": str(start), "end": str(end),
        "calendar": "source civil dates; sleep assigned to waking day", "metrics": {
            name: _evidence(name, days, {}, today, now) for name in dict.fromkeys(metrics)}}
    try:
        directory = profile_directory(profile, home_dir)
        auth = credentials(directory, profile.slug)
        if auth is None:
            return result
        clock_zone = ZoneInfo(auth["timezone"])
        today = datetime.now(clock_zone).date()
        if end > today:
            raise GoogleHealthError("unavailable", "Google Health requests cannot extend beyond today in the connection timezone.")
        with profile_lock(directory):
            # Reload after obtaining the lock, in case another command refreshed credentials.
            auth = credentials(directory, profile.slug)
            if auth is None:
                return result
            binding = json.dumps([profile.slug, auth["subject"], auth["health_user_id"]])
            client = AuthorizedClient(directory, home_dir, auth)
            cache = CoverageCache(directory, binding)
            try:
                for name in result["metrics"]:
                    cached = cache.days(name)
                    if not offline:
                        for first, last in _windows(start, end, METRICS[name], cached, today, refresh):
                            try:
                                rows = _fetch(client, name, first, last)
                                cache.save(name, rows, now)
                            except GoogleHealthError as exc:
                                cache.fail(name, calendar_days(first, last), exc.status)
                                break
                    result["metrics"][name] = _evidence(name, days, cache.days(name), today, now,
                                                         offline=offline, clock_zone=clock_zone)
                if not offline:
                    write_private(directory / "last-request.json", {
                        "start": str(start), "end": str(end), "metrics": list(result["metrics"]), "binding": binding,
                    })
            finally:
                cache.close()
        statuses = {item["status"] for item in result["metrics"].values()}
        result["status"] = "available" if statuses == {"complete"} else "stale" if statuses <= {"complete", "stale"} else "partial"
    except GoogleHealthError as exc:
        result["status"], result["message"] = exc.status, str(exc)
    except (OSError, sqlite3.Error):
        result["status"], result["message"] = "unreadable", "Google Health cache is unreadable; existing history was preserved."
    return result


def cached_evidence(profile: ProfileContext) -> dict[str, Any]:
    """Return the last selected evidence window without network requests or credential disclosure."""
    if profile.wearable_evidence is not None:
        return profile.wearable_evidence
    result: dict[str, Any] = {"status": "not configured", "source_type": "google_health", "metrics": {}}
    if profile.home_dir is None:
        return result
    try:
        directory = profile_directory(profile, profile.home_dir)
        auth = credentials(directory, profile.slug)
        if auth:
            result["status"] = "missing"
            result["message"] = "Connected, but no wearable date/metric window has been retrieved."
            path = directory / "last-request.json"
            if path.exists():
                request = read_private(path)
                binding = json.dumps([profile.slug, auth["subject"], auth["health_user_id"]])
                if request.get("binding") != binding:
                    raise GoogleHealthError("unavailable", "Cached wearable request has a different identity binding.")
                result = retrieve(profile=profile, home_dir=profile.home_dir,
                                  start=date.fromisoformat(request["start"]), end=date.fromisoformat(request["end"]),
                                  metrics=request["metrics"], offline=True)
                result["retrieval_mode"] = "cached only"
    except GoogleHealthError as exc:
        result["status"], result["message"] = exc.status, str(exc)
    except (ValueError, KeyError, TypeError):
        result["status"], result["message"] = "unreadable", "Cached wearable request is invalid."
    profile.wearable_evidence = result
    return result


def source_metadata(profile: ProfileContext) -> dict[str, Any]:
    evidence = cached_evidence(profile)
    details = {name: {key: value for key, value in metric.items() if key != "records"}
               | {"record_count": len(metric["records"])}
               for name, metric in evidence["metrics"].items()}
    fetched = [day["fetched_at"] for metric in details.values() for day in metric.get("coverage", {}).values()
               if day.get("fetched_at")]
    return {"status": evidence["status"], "path": "", "sample": [], "details": details,
            "latest_modified_at": max(fetched, default=None), "message": evidence.get("message", ""),
            "start": evidence.get("start"), "end": evidence.get("end")}
