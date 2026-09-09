from __future__ import annotations

import json
from pathlib import Path

from healthpilot.cli import main


def runtime(tmp_path: Path, slug: str = "alice") -> tuple[Path, list[str]]:
    home = tmp_path / "home"
    profiles = home / ".config/healthpilot/profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / f"{slug}.yaml").write_text(f"name: {slug}\ndata_sources: {{}}\n")
    return home, ["--home-dir", str(home), "--repo-root", str(tmp_path / "repo")]


def test_unconnected_profile_returns_honest_unavailable_evidence(tmp_path, capsys):
    _, args = runtime(tmp_path)
    result = main(args + ["google-health", "--profile", "alice", "--metrics", "hrv",
                          "--start", "2026-01-01", "--end", "2026-01-02"])
    evidence = json.loads(capsys.readouterr().out)
    assert result == 0
    assert evidence["status"] == "not configured"
    assert evidence["metrics"]["hrv"]["records"] == []
    assert evidence["metrics"]["hrv"]["missing_days"] == ["2026-01-01", "2026-01-02"]
    assert not (tmp_path / "home/.config/healthpilot/google-health").exists()


def test_connect_binds_verified_account_and_private_credentials(tmp_path, monkeypatch, capsys):
    import http.client
    import io
    import threading
    import urllib.parse

    home, args = runtime(tmp_path)
    client_file = tmp_path / "client.json"
    client_file.write_text(json.dumps({"installed": {"client_id": "shared-client",
                                                   "client_secret": "shared-secret"}}))
    assert main(args + ["google-health-configure", "--client-file", str(client_file)]) == 0
    capsys.readouterr()
    scopes = []
    requests = []
    threads = []
    person = "alice"
    returned_email = "alice@example.com"

    def open_browser(url):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        scopes.extend(query["scope"][0].split())
        assert query["code_challenge_method"] == ["S256"]
        assert query["access_type"] == ["offline"]
        assert query["login_hint"] == [person + "@example.com"]
        redirect = urllib.parse.urlsplit(query["redirect_uri"][0])

        def callback():
            conn = http.client.HTTPConnection(redirect.hostname, redirect.port, timeout=5)
            conn.request("GET", redirect.path + "?" + urllib.parse.urlencode(
                {"code": "consented-code", "state": query["state"][0]}))
            conn.getresponse().read()
            conn.close()

        thread = threading.Thread(target=callback)
        threads.append(thread)
        thread.start()
        return True

    def network(request, **kwargs):
        requests.append(request)
        if request.full_url == "https://oauth2.googleapis.com/token":
            assert b"code_verifier=" in request.data
            body = {"access_token": person + "-access", "refresh_token": person + "-refresh",
                    "expires_in": 3600, "scope": " ".join(scopes)}
        elif request.full_url == "https://openidconnect.googleapis.com/v1/userinfo":
            body = {"sub": person + "-sub", "email": returned_email, "email_verified": True}
        elif request.full_url == "https://health.googleapis.com/v4/users/me/identity":
            body = {"healthUserId": person + "-health"}
        else:
            raise AssertionError(request.full_url)
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr("webbrowser.open", open_browser)
    monkeypatch.setattr("urllib.request.urlopen", network)
    assert main(args + ["google-health-connect", "--profile", "alice",
                        "--account", "alice@example.com", "--timezone", "Europe/Lisbon"]) == 0
    for thread in threads:
        thread.join(timeout=5)
    connected = json.loads(capsys.readouterr().out)
    assert connected["account"] == "alice@example.com"
    assert all(scope in {"openid", "email"} or scope.endswith(".readonly") for scope in scopes)
    auth = home / ".config/healthpilot/google-health/profiles/alice/credentials.json"
    assert auth.stat().st_mode & 0o777 == 0o600
    assert auth.parent.stat().st_mode & 0o777 == 0o700
    saved = json.loads(auth.read_text())
    assert saved["profile_slug"] == "alice"
    assert saved["subject"] == "alice-sub"
    assert saved["health_user_id"] == "alice-health"
    assert saved["refresh_token"] == "alice-refresh"
    assert "alice-access" not in json.dumps(connected)

    # Authorize a second account through the same app, leaving Alice's binding untouched.
    runtime(tmp_path, "bob")
    person, returned_email = "bob", "bob@example.com"
    assert main(args + ["google-health-connect", "--profile", "bob",
                        "--account", "bob@example.com"]) == 0
    bob = json.loads(capsys.readouterr().out)
    assert bob["account"] == "bob@example.com"
    assert json.loads(auth.read_text()) == saved
    bob_path = auth.parent.parent / "bob/credentials.json"
    before = bob_path.read_text()
    assert json.loads(before)["subject"] == "bob-sub"
    assert json.loads(before)["client_id"] == saved["client_id"]

    # A different account selected in the browser cannot silently replace the binding.
    import pytest
    returned_email = "unexpected@example.com"
    with pytest.raises(SystemExit) as error:
        main(args + ["google-health-connect", "--profile", "bob", "--account", "bob@example.com"])
    assert error.value.code == 2
    assert "does not match" in capsys.readouterr().err
    assert bob_path.read_text() == before
    for thread in threads:
        thread.join(timeout=5)


def seed_connection(home: Path, slug: str = "alice", *, scopes=None, expired=False):
    import time
    from healthpilot.google_health_auth import SCOPES

    root = home / ".config/healthpilot/google-health"
    directory = root / "profiles" / slug
    directory.mkdir(parents=True, exist_ok=True)
    (root / "application.json").write_text(json.dumps({"client_id": "shared-client", "client_secret": "shared-secret"}))
    (directory / "credentials.json").write_text(json.dumps({
        "profile_slug": slug, "subject": slug + "-sub", "health_user_id": slug + "-health",
        "account": slug + "@example.com", "timezone": "Europe/Lisbon", "client_id": "shared-client",
        "access_token": slug + "-access", "refresh_token": slug + "-refresh",
        "expires_at": 0 if expired else time.time() + 3600, "scopes": list(SCOPES) if scopes is None else scopes,
    }))


def query(args, capsys, *, slug="alice", metric="hrv", start="2026-01-05", end="2026-01-05", extra=()):
    assert main(args + ["google-health", "--profile", slug, "--metrics", metric,
                        "--start", start, "--end", end, *extra]) == 0
    return json.loads(capsys.readouterr().out)


def hrv(day=5, value=42):
    return {"dailyHeartRateVariability": {"date": {"year": 2026, "month": 1, "day": day},
                                          "averageHeartRateVariabilityMilliseconds": value}}


def test_historical_cache_reuses_broader_coverage_and_isolates_people(tmp_path, monkeypatch, capsys):
    import io
    import urllib.parse

    home, args = runtime(tmp_path)
    runtime(tmp_path, "bob")
    seed_connection(home)
    seed_connection(home, "bob")
    calls = []

    def network(request, **kwargs):
        calls.append(request)
        assert request.full_url.startswith("https://health.googleapis.com/v4/users/me/dataTypes/daily-heart-rate-variability/dataPoints:reconcile?")
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        assert 'daily_heart_rate_variability.date >= "2026-01-01"' in params["filter"][0]
        person = request.get_header("Authorization")
        return io.BytesIO(json.dumps({"dataPoints": [hrv(5, 42 if person == "Bearer alice-access" else 18), hrv(6, 43)]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    first = query(args, capsys)
    assert first["metrics"]["hrv"]["records"][0]["data"]["averageHeartRateVariabilityMilliseconds"] == 42
    assert first["metrics"]["hrv"]["status"] == "complete"
    again = query(args, capsys, start="2026-01-06", end="2026-01-06")
    assert again["metrics"]["hrv"]["records"][0]["data"]["averageHeartRateVariabilityMilliseconds"] == 43
    assert len(calls) == 1
    bob = query(args, capsys, slug="bob")
    assert bob["metrics"]["hrv"]["records"][0]["data"]["averageHeartRateVariabilityMilliseconds"] == 18
    assert len(calls) == 2
    assert "alice-access" not in json.dumps(first)
    assert "bob" not in json.dumps(first)


def test_expired_token_refreshes_only_when_uncached_evidence_is_needed(tmp_path, monkeypatch, capsys):
    import io
    import urllib.parse
    from healthpilot.google_health_auth import SCOPES

    home, args = runtime(tmp_path)
    seed_connection(home, expired=True)
    requests = []

    def network(request, **kwargs):
        requests.append(request)
        if request.full_url == "https://oauth2.googleapis.com/token":
            form = urllib.parse.parse_qs(request.data.decode())
            assert form["refresh_token"] == ["alice-refresh"]
            assert form["grant_type"] == ["refresh_token"]
            body = {"access_token": "renewed-access", "refresh_token": "rotated-refresh", "expires_in": 3600,
                    "scope": " ".join(SCOPES)}
        elif request.full_url.endswith("/userinfo"):
            body = {"sub": "alice-sub", "email": "alice@example.com", "email_verified": True}
        elif request.full_url.endswith("/identity"):
            body = {"healthUserId": "alice-health"}
        else:
            assert request.get_header("Authorization") == "Bearer renewed-access"
            body = {"dataPoints": [hrv()]}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    result = query(args, capsys)
    assert result["status"] == "available"
    auth = json.loads((home / ".config/healthpilot/google-health/profiles/alice/credentials.json").read_text())
    assert auth["refresh_token"] == "rotated-refresh"
    count = len(requests)
    query(args, capsys)
    assert len(requests) == count
    assert "renewed-access" not in json.dumps(result)


def test_recent_days_refresh_and_failed_pagination_preserves_complete_history(tmp_path, monkeypatch, capsys):
    import io
    import urllib.error
    from datetime import datetime
    from zoneinfo import ZoneInfo

    home, args = runtime(tmp_path)
    seed_connection(home)
    today = datetime.now(ZoneInfo("Europe/Lisbon")).date()
    point = {"dailyHeartRateVariability": {"date": {"year": today.year, "month": today.month, "day": today.day},
                                          "averageHeartRateVariabilityMilliseconds": 42}}
    calls = []
    mode = "success"

    def network(request, **kwargs):
        calls.append(request)
        if mode == "partial" and "pageToken=" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 503, "secret-error-body", {}, io.BytesIO(b"alice-refresh"))
        body = {"dataPoints": [point, point]}
        if mode == "partial":
            body["nextPageToken"] = "next-page"
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    monkeypatch.setattr("time.sleep", lambda _: None)
    first = query(args, capsys, start=str(today), end=str(today))
    assert len(first["metrics"]["hrv"]["records"]) == 1
    point["dailyHeartRateVariability"]["averageHeartRateVariabilityMilliseconds"] = 55
    fresh = query(args, capsys, start=str(today), end=str(today))
    assert fresh["metrics"]["hrv"]["records"][0]["data"]["averageHeartRateVariabilityMilliseconds"] == 55
    assert len(calls) == 2
    mode = "partial"
    point["dailyHeartRateVariability"]["averageHeartRateVariabilityMilliseconds"] = 99
    failed = query(args, capsys, start=str(today), end=str(today))
    assert failed["status"] == "stale"
    assert failed["metrics"]["hrv"]["stale_days"] == [str(today)]
    assert failed["metrics"]["hrv"]["records"][0]["data"]["averageHeartRateVariabilityMilliseconds"] == 55
    assert "secret-error-body" not in json.dumps(failed)
    assert "alice-refresh" not in json.dumps(failed)


def test_empty_history_is_cached_and_explicit_refresh_can_replace_it(tmp_path, monkeypatch, capsys):
    import io
    home, args = runtime(tmp_path)
    seed_connection(home)
    calls = []
    rows = []

    def network(request, **kwargs):
        calls.append(request)
        return io.BytesIO(json.dumps({"dataPoints": rows}).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    empty = query(args, capsys)
    assert empty["metrics"]["hrv"]["empty_days"] == ["2026-01-05"]
    assert empty["metrics"]["hrv"]["missing_days"] == []
    rows.append(hrv())
    cached = query(args, capsys)
    assert cached["metrics"]["hrv"]["records"] == []
    assert len(calls) == 1
    refreshed = query(args, capsys, extra=["--refresh"])
    assert len(calls) == 2
    assert refreshed["metrics"]["hrv"]["records"][0]["data"]["averageHeartRateVariabilityMilliseconds"] == 42


def test_missing_permission_does_not_make_api_requests(tmp_path, monkeypatch, capsys):
    home, args = runtime(tmp_path)
    seed_connection(home, scopes=["openid", "email"])
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Unexpected network")))
    result = query(args, capsys)
    assert result["status"] == "partial"
    assert result["metrics"]["hrv"]["errors"] == ["permission denied"]
    assert result["metrics"]["hrv"]["missing_days"] == ["2026-01-05"]


def test_paginated_samples_keep_source_timezone_and_unique_measurements(tmp_path, monkeypatch, capsys):
    import io
    import urllib.parse

    home, args = runtime(tmp_path)
    seed_connection(home)
    requests = []
    point = {"heartRate": {"sampleTime": {"physicalTime": "2026-01-04T23:30:00Z", "utcOffset": "3600s"},
                           "beatsPerMinute": "63", "metadata": {"motionContext": "SEDENTARY"}}}

    def network(request, **kwargs):
        requests.append(request)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        assert params["filter"] == ['heart_rate.sample_time.civil_time >= "2026-01-05" AND heart_rate.sample_time.civil_time < "2026-01-06"']
        body = {"dataPoints": [point]}
        if "pageToken" not in params:
            body["nextPageToken"] = "second"
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    result = query(args, capsys, metric="heart-rate")
    assert len(requests) == 2
    records = result["metrics"]["heart-rate"]["records"]
    assert len(records) == 1
    assert records[0]["observed_at"] == "2026-01-05"
    assert records[0]["data"]["sampleTime"] == {"physicalTime": "2026-01-04T23:30:00Z", "utcOffset": "3600s"}
    assert records[0]["citation_id"].startswith("[WEARABLE:")


def test_normal_evidence_packet_includes_wearables_and_hides_credentials(tmp_path, monkeypatch, capsys):
    import io
    home, args = runtime(tmp_path)
    seed_connection(home)
    calls = []

    def network(request, **kwargs):
        calls.append(request)
        return io.BytesIO(json.dumps({"dataPoints": [hrv()]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    assert main(args + ["plan", "--profile", "alice", "--wearable-metrics", "hrv",
                        "--wearable-start", "2026-01-05", "--wearable-end", "2026-01-05"]) == 0
    capsys.readouterr()
    state = tmp_path / "repo/.state/profiles/alice"
    packet = json.loads((state / "evidence-packet.json").read_text())
    wearable = packet["wearables"]
    assert wearable["status"] == "available"
    assert packet["source_snapshot"]["sources"]["google_health"]["status"] == "available"
    assert wearable["metrics"]["hrv"]["records"][0]["citation_id"] in packet["citation_index"]
    # An ordinary packet reuses the selected historical evidence without a network request.
    assert main(args + ["evidence-packet", "--profile", "alice"]) == 0
    again = json.loads((state / "evidence-packet.json").read_text())
    assert again["wearables"]["metrics"]["hrv"]["records"] == wearable["metrics"]["hrv"]["records"]
    assert len(calls) == 1
    for path in state.glob("*.json"):
        text = path.read_text()
        assert "alice-access" not in text
        assert "alice-refresh" not in text
        assert "shared-secret" not in text
        assert "alice@example.com" not in text
        assert "credentials.json" not in text


def test_weight_sleep_activity_and_calories_use_verified_api_shapes(tmp_path, monkeypatch, capsys):
    import io
    import urllib.parse
    from datetime import date

    home, args = runtime(tmp_path)
    seed_connection(home)
    requests = []

    def network(request, **kwargs):
        requests.append(request)
        if "/weight/" in request.full_url:
            body = {"dataPoints": [{"weight": {"sampleTime": {"physicalTime": "2026-01-05T08:00:00Z", "utcOffset": "0s"}, "weightGrams": 75000}}]}
        elif "/sleep/" in request.full_url:
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
            assert params["pageSize"] == ["25"]
            assert "sleep.interval.civil_end_time" in params["filter"][0]
            body = {"dataPoints": [{"sleep": {"interval": {"startTime": "2026-01-04T23:00:00Z", "endTime": "2026-01-05T07:00:00Z", "startUtcOffset": "0s", "endUtcOffset": "0s"}, "summary": {"minutesAsleep": "450"}}}]}
        else:
            assert request.get_method() == "POST"
            assert request.full_url.endswith(":dailyRollUp")
            request_body = json.loads(request.data)
            interval = request_body["range"]
            first, last = (date(**interval[side]["date"]) for side in ("start", "end"))
            if "/total-calories/" in request.full_url:
                assert (last - first).days <= 14
                value = {"totalCalories": {"kcalSum": 2300}}
            else:
                value = {"steps": {"countSum": "7500"}}
            body = {"rollupDataPoints": [{"civilStartTime": {"date": {"year": 2026, "month": 1, "day": 5}},
                                         "civilEndTime": {"date": {"year": 2026, "month": 1, "day": 6}}, **value}]}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    for metric, key, expected in [("weight", "weightGrams", 75000), ("sleep", "summary", {"minutesAsleep": "450"}),
                                   ("steps", "countSum", "7500"), ("calories", "kcalSum", 2300)]:
        result = query(args, capsys, metric=metric)
        assert result["status"] == "available"
        records = result["metrics"][metric]["records"]
        assert len(records) == 1
        assert records[0]["data"][key] == expected
        assert records[0]["observed_at"] == "2026-01-05"
    assert len(requests) == 4


def test_revoked_authorization_preserves_cache_and_requests_reconnection(tmp_path, monkeypatch, capsys):
    import io
    import urllib.error

    home, args = runtime(tmp_path)
    seed_connection(home)
    mode = "ok"

    def network(request, **kwargs):
        if mode == "revoked":
            code = 400 if request.full_url.endswith("/token") else 401
            raise urllib.error.HTTPError(request.full_url, code, "failure", {}, io.BytesIO(b"refresh-secret"))
        return io.BytesIO(json.dumps({"dataPoints": [hrv()]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", network)
    query(args, capsys)
    mode = "revoked"
    result = query(args, capsys, extra=["--refresh"])
    assert result["status"] == "stale"
    assert result["metrics"]["hrv"]["errors"] == ["reconnect required"]
    assert len(result["metrics"]["hrv"]["records"]) == 1
    assert "refresh-secret" not in json.dumps(result)


def test_external_profile_cannot_borrow_live_profile_connection(tmp_path, monkeypatch, capsys):
    home, args = runtime(tmp_path)
    seed_connection(home)
    outside = tmp_path / "alice.yaml"
    outside.write_text("name: Different person\ndata_sources: {}\n")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Unexpected network")))
    result = query(args, capsys, slug=str(outside))
    assert result["status"] == "unavailable"
    assert result["metrics"]["hrv"]["records"] == []


def test_cache_identity_mismatch_never_returns_another_person(tmp_path, monkeypatch, capsys):
    import io
    import shutil
    home, args = runtime(tmp_path)
    runtime(tmp_path, "bob")
    seed_connection(home)
    seed_connection(home, "bob")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: io.BytesIO(json.dumps({"dataPoints": [hrv()]}).encode()))
    query(args, capsys)
    directory = home / ".config/healthpilot/google-health/profiles"
    shutil.copyfile(directory / "alice/measurements.sqlite3", directory / "bob/measurements.sqlite3")
    result = query(args, capsys, slug="bob")
    assert result["status"] == "unavailable"
    assert result["metrics"]["hrv"]["records"] == []


def test_unreadable_connection_does_not_crash_retrieval(tmp_path, capsys):
    home, args = runtime(tmp_path)
    seed_connection(home)
    path = home / ".config/healthpilot/google-health/profiles/alice/credentials.json"
    auth = json.loads(path.read_text())
    auth.pop("timezone")
    path.write_text(json.dumps(auth))
    result = query(args, capsys)
    assert result["status"] == "unreadable"
    assert result["metrics"]["hrv"]["records"] == []


def test_cached_recent_evidence_becomes_stale_on_profile_local_next_day(tmp_path, monkeypatch, capsys):
    import io
    from datetime import datetime, timezone

    class Clock(datetime):
        current = datetime(2026, 9, 9, 3, tzinfo=timezone.utc)  # Sep 8, 20:00 in Los Angeles.

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    home, args = runtime(tmp_path)
    seed_connection(home)
    auth_path = home / ".config/healthpilot/google-health/profiles/alice/credentials.json"
    auth = json.loads(auth_path.read_text())
    auth["timezone"] = "America/Los_Angeles"
    auth_path.write_text(json.dumps(auth))
    monkeypatch.setattr("healthpilot.google_health.datetime", Clock)
    point = {"dailyHeartRateVariability": {"date": {"year": 2026, "month": 9, "day": 8}, "averageHeartRateVariabilityMilliseconds": 42}}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: io.BytesIO(json.dumps({"dataPoints": [point]}).encode()))
    result = query(args, capsys, start="2026-09-08", end="2026-09-08")
    assert result["status"] == "available"
    Clock.current = datetime(2026, 9, 9, 19, tzinfo=timezone.utc)  # Sep 9, noon local.
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Unexpected network")))
    assert main(args + ["evidence-packet", "--profile", "alice"]) == 0
    packet = json.loads((tmp_path / "repo/.state/profiles/alice/evidence-packet.json").read_text())
    assert packet["wearables"]["status"] == "stale"
    assert packet["wearables"]["metrics"]["hrv"]["stale_days"] == ["2026-09-08"]


def test_symlinked_runtime_root_cannot_redirect_cache_writes(tmp_path, monkeypatch, capsys):
    home, args = runtime(tmp_path)
    seed_connection(home)
    original = home / ".config/healthpilot/google-health"
    external = tmp_path / "external"
    original.rename(external)
    original.symlink_to(external, target_is_directory=True)
    before = sorted(str(p.relative_to(external)) for p in external.rglob("*"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Unexpected network")))
    result = query(args, capsys)
    assert result["status"] == "unreadable"
    assert sorted(str(p.relative_to(external)) for p in external.rglob("*")) == before
