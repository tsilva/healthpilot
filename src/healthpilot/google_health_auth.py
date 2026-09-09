"""Local Google OAuth, private runtime storage, and a redacted HTTP boundary."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import math
import os
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from healthpilot.paths import profiles_dir
from healthpilot.profile import ProfileContext

API = "https://health.googleapis.com/v4"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE_PREFIX = "https://www.googleapis.com/auth/googlehealth."
HEALTH_SCOPES = tuple(SCOPE_PREFIX + group + ".readonly" for group in (
    "health_metrics_and_measurements", "activity_and_fitness", "sleep",
))
SCOPES = ("openid", "email", *HEALTH_SCOPES)


class GoogleHealthError(ValueError):
    """Safe, actionable error text; never contains a remote response body."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def runtime_root(home_dir: Path) -> Path:
    root = home_dir
    for part in (".config", "healthpilot", "google-health"):
        root = root / part
        if root.is_symlink():
            raise GoogleHealthError("unreadable", "Google Health runtime directories must not be symbolic links.")
    return root


def profile_directory(profile: ProfileContext, home_dir: Path) -> Path:
    canonical = profiles_dir(home_dir) / f"{profile.slug}.yaml"
    # Do not let a development/external profile borrow a live profile's credentials.
    if profile.path.resolve() != canonical.absolute() or canonical.is_symlink():
        raise GoogleHealthError("unavailable", "Google Health requires a canonical local runtime profile.")
    root = runtime_root(home_dir)
    directory = root / "profiles" / profile.slug
    if directory.parent.is_symlink() or directory.is_symlink():
        raise GoogleHealthError("unreadable", "Google Health runtime directories must not be symbolic links.")
    return directory


def private_directory(path: Path) -> None:
    if not path.parent.exists():
        private_directory(path.parent)
    if path.is_symlink():
        raise GoogleHealthError("unreadable", "Google Health storage must not be a symbolic link.")
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)


def read_private(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise GoogleHealthError("unreadable", "Google Health storage must not be a symbolic link.")
    try:
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except (OSError, ValueError):
        raise GoogleHealthError("unreadable", "Google Health runtime file is missing, unreadable or invalid.") from None


def write_private(path: Path, payload: dict[str, Any]) -> None:
    private_directory(path.parent)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def profile_lock(directory: Path) -> Iterator[None]:
    private_directory(directory)
    fd = os.open(directory / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def request_json(url: str, *, token: str = "", form: dict[str, Any] | None = None,
                 body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            if not isinstance(payload, dict) or "error" in payload:
                raise GoogleHealthError("partial", "Google Health returned an invalid response.")
            return payload
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            if code == 401 or (url == TOKEN_URL and code == 400):
                raise GoogleHealthError("reconnect required", "Google authorization expired or was revoked; reconnect this profile.") from None
            if code == 403:
                raise GoogleHealthError("permission denied", "Google Health denied access; check granted read permissions and API setup.") from None
            if (code == 429 or code >= 500) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise GoogleHealthError("unavailable", f"Google Health request failed (HTTP {code}); retry later or check API setup.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise GoogleHealthError("unavailable", "Google Health network request failed; retry later.") from None
        except (ValueError, UnicodeError) as exc:
            if isinstance(exc, GoogleHealthError):
                raise
            raise GoogleHealthError("partial", "Google Health returned an invalid response.") from None
    raise AssertionError("unreachable")


def configure(home_dir: Path, client_file: Path) -> None:
    config = read_private(client_file).get("installed", {})
    if not config.get("client_id") or not config.get("client_secret"):
        raise GoogleHealthError("not configured", "Use a downloaded Google OAuth Desktop app client JSON.")
    write_private(runtime_root(home_dir) / "application.json", {
        "client_id": config["client_id"], "client_secret": config["client_secret"],
    })


def credentials(directory: Path, profile_slug: str) -> dict[str, Any] | None:
    path = directory / "credentials.json"
    if not path.exists():
        return None
    auth = read_private(path)
    if auth.get("profile_slug") != profile_slug or not auth.get("subject") or not auth.get("health_user_id"):
        raise GoogleHealthError("unavailable", "Google Health identity binding is invalid; reconnect this profile.")
    try:
        for field in ("subject", "health_user_id", "account", "timezone", "client_id", "access_token", "refresh_token"):
            if not isinstance(auth[field], str) or not auth[field]:
                raise ValueError
        ZoneInfo(auth["timezone"])
        if not isinstance(auth["expires_at"], (int, float)) or not math.isfinite(auth["expires_at"]):
            raise ValueError
        if not isinstance(auth["scopes"], list) or not all(isinstance(scope, str) for scope in auth["scopes"]):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise GoogleHealthError("unreadable", "Google Health credentials are invalid; reconnect this profile.") from None
    return auth


def _authorization_code(client: dict[str, Any], account: str) -> tuple[str, str, str]:
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    result: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            valid = parsed.path == "/callback" and secrets.compare_digest(query.get("state", [""])[0], state)
            if valid:
                result["code"] = query.get("code", [""])[0]
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Authorization received. Return to Healthpilot." if valid else b"Invalid OAuth callback.")

        def log_message(self, format: str, *args: Any) -> None:
            pass  # Callback URLs contain authorization codes.

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        redirect = f"http://127.0.0.1:{server.server_port}/callback"
        query = urllib.parse.urlencode({
            "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
            "scope": " ".join(SCOPES), "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "access_type": "offline",
            "prompt": "consent select_account", "login_hint": account,
        })
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + query
        print("Authorize the selected account in your browser. Waiting up to 3 minutes.", file=sys.stderr)
        if not webbrowser.open(url):
            print(f"Open this authorization URL locally: {url}", file=sys.stderr)
        deadline = time.monotonic() + 180
        while "code" not in result and time.monotonic() < deadline:
            server.timeout = min(1, max(0, deadline - time.monotonic()))
            server.handle_request()
    if not result.get("code"):
        raise GoogleHealthError("reconnect required", "Google authorization was declined or timed out; retry connection.")
    return result["code"], redirect, verifier


def connect(profile: ProfileContext, home_dir: Path, account: str, timezone: str) -> dict[str, Any]:
    try:
        ZoneInfo(timezone)
    except (KeyError, ValueError):
        raise GoogleHealthError("unavailable", "Use a valid IANA timezone, such as Europe/Lisbon or UTC.") from None
    directory = profile_directory(profile, home_dir)
    client = read_private(runtime_root(home_dir) / "application.json")
    with profile_lock(directory):
        code, redirect, verifier = _authorization_code(client, account)
        token = request_json(TOKEN_URL, form={**client, "code": code, "redirect_uri": redirect,
                             "code_verifier": verifier, "grant_type": "authorization_code"})
        access = token.get("access_token", "")
        if not access or not token.get("refresh_token"):
            raise GoogleHealthError("reconnect required", "Offline authorization was not granted; reconnect with consent.")
        identity = request_json(USERINFO_URL, token=access)
        if identity.get("email_verified") is not True or not identity.get("sub") or identity.get("email", "").casefold() != account.casefold():
            raise GoogleHealthError("reconnect required", "Authorized Google account does not match the requested verified email; connection was not saved.")
        health = request_json(f"{API}/users/me/identity", token=access)
        if not health.get("healthUserId"):
            raise GoogleHealthError("reconnect required", "Google Health did not return a verified health identity.")
        old = credentials(directory, profile.slug)
        if old and (old["subject"] != identity["sub"] or old["health_user_id"] != health["healthUserId"]):
            raise GoogleHealthError("reconnect required", "This profile is bound to a different account. Remove its Google Health runtime directory before linking another person.")
        auth = {
            "profile_slug": profile.slug, "subject": identity["sub"], "account": identity["email"],
            "health_user_id": health["healthUserId"], "timezone": timezone,
            "client_id": client["client_id"], "access_token": access,
            "refresh_token": token["refresh_token"], "expires_at": time.time() + float(token.get("expires_in", 0)),
            "scopes": token.get("scope", "").split(),
        }
        write_private(directory / "credentials.json", auth)
    return connection_status(profile, home_dir)


def connection_status(profile: ProfileContext, home_dir: Path) -> dict[str, Any]:
    try:
        auth = credentials(profile_directory(profile, home_dir), profile.slug)
        if auth is None:
            return {"status": "not configured", "profile_slug": profile.slug}
        return {"status": "connected", "profile_slug": profile.slug, "account": auth["account"],
                "timezone": auth["timezone"], "granted_scopes": auth["scopes"],
                "missing_scopes": sorted(set(HEALTH_SCOPES) - set(auth["scopes"]))}
    except GoogleHealthError as exc:
        return {"status": exc.status, "profile_slug": profile.slug, "message": str(exc)}


class AuthorizedClient:
    """Resolve each network request through one locked profile's authorization."""

    def __init__(self, directory: Path, home_dir: Path, auth: dict[str, Any]):
        self.directory, self.home_dir, self.auth = directory, home_dir, auth

    def refresh(self) -> None:
        client = read_private(runtime_root(self.home_dir) / "application.json")
        if client.get("client_id") != self.auth.get("client_id"):
            raise GoogleHealthError("reconnect required", "Shared OAuth app changed; reconnect this profile.")
        token = request_json(TOKEN_URL, form={**client, "grant_type": "refresh_token",
                             "refresh_token": self.auth["refresh_token"]})
        access = token.get("access_token")
        if not access:
            raise GoogleHealthError("reconnect required", "Google did not renew access; reconnect this profile.")
        identity = request_json(USERINFO_URL, token=access)
        health = request_json(f"{API}/users/me/identity", token=access)
        if identity.get("sub") != self.auth["subject"] or health.get("healthUserId") != self.auth["health_user_id"]:
            raise GoogleHealthError("reconnect required", "Renewed Google identity does not match this profile; reconnect it.")
        self.auth.update(access_token=access, expires_at=time.time() + float(token.get("expires_in", 0)),
                         refresh_token=token.get("refresh_token") or self.auth["refresh_token"],
                         scopes=token["scope"].split() if "scope" in token else self.auth["scopes"])
        write_private(self.directory / "credentials.json", self.auth)

    def request(self, url: str, *, scope: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if scope not in self.auth["scopes"]:
            raise GoogleHealthError("permission denied", "Metric read permission is missing; reconnect and grant the requested read permissions.")
        refreshed = False
        if self.auth.get("expires_at", 0) <= time.time() + 60:
            self.refresh()
            refreshed = True
        if scope not in self.auth["scopes"]:
            raise GoogleHealthError("permission denied", "Renewed authorization lacks this metric's read permission.")
        try:
            return request_json(url, token=self.auth["access_token"], body=body)
        except GoogleHealthError as exc:
            if exc.status != "reconnect required" or refreshed:
                raise
            self.refresh()
            if scope not in self.auth["scopes"]:
                raise GoogleHealthError("permission denied", "Renewed authorization lacks this metric's read permission.") from None
            return request_json(url, token=self.auth["access_token"], body=body)
