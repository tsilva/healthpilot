"""Filesystem helpers for repo-local state and runtime profile discovery."""

from __future__ import annotations

from pathlib import Path


def expand_home(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def repo_path(repo_root: Path, *parts: str) -> Path:
    return repo_root.joinpath(*parts)


def state_path(repo_root: Path, *parts: str) -> Path:
    return repo_path(repo_root, ".state", *parts)


def profiles_state_path(repo_root: Path, profile_slug: str, *parts: str) -> Path:
    return state_path(repo_root, "profiles", profile_slug, *parts)


def output_path(repo_root: Path, *parts: str) -> Path:
    return repo_path(repo_root, ".output", *parts)


def profile_output_path(repo_root: Path, profile_slug: str, *parts: str) -> Path:
    return output_path(repo_root, profile_slug, *parts)


def profiles_dir(home_dir: Path) -> Path:
    return home_dir.joinpath(".config", "healthpilot", "profiles")


def ensure_repo_dirs(repo_root: Path, profile_slug: str) -> None:
    profiles_state_path(repo_root, profile_slug).mkdir(parents=True, exist_ok=True)
    output_path(repo_root, profile_slug).mkdir(parents=True, exist_ok=True)
