"""
update_checker.py - Lightweight app update checks via GitHub Releases API.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


GITHUB_OWNER = "DeKairos"
GITHUB_REPO = "Taskbar_Audio-_Visualizer"
DEFAULT_VERSION = "0.0.0"
RELEASES_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
TAGS_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/tags"
RELEASES_LATEST_WEB_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
INSTALLER_ASSET_REGEX = re.compile(r"^AudioVisualizer-Setup-.*\\.exe$", re.IGNORECASE)


def _parse_semver(value: str) -> tuple[int, int, int]:
    """Extract and normalize x.y.z from values like v1.2.3 or 1.2.3-beta."""
    if not value:
        return (0, 0, 0)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _is_valid_semver(value: str) -> bool:
    """Return True for semver-like values such as 1.2.3 or 1.2.3-rc.1."""
    return bool(re.match(r"^\d+\.\d+\.\d+([+-][0-9A-Za-z.-]+)?$", value or ""))


def _current_version_from_git(timeout: float = 2.5) -> str | None:
    """Best-effort app version for dev runs from the latest reachable semver tag."""
    base_dir = os.path.dirname(__file__)
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
            cwd=base_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        ).stdout.strip()
        if not out:
            return None
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def _select_highest_semver_tag(tag_names: list[str]) -> str:
    """Pick the highest semver-like tag name from a list of tag names."""
    best_name = ""
    best_semver = (0, 0, 0)
    for name in tag_names:
        sem = _parse_semver(name)
        if sem > best_semver:
            best_semver = sem
            best_name = name
    return best_name


def get_current_version() -> str:
    """Return installed app version, env override, git tag fallback, or default."""
    if getattr(sys, "frozen", False):
        try:
            base = os.path.dirname(sys.executable)
            version_file = os.path.join(base, "VERSION.txt")
            if os.path.exists(version_file):
                with open(version_file, "r", encoding="utf-8") as f:
                    first = f.readline().strip()
                m = re.search(r"(\d+\.\d+\.\d+)", first)
                if m:
                    return m.group(1)
        except Exception:
            pass

    env_version = os.getenv("AUDIO_VISUALIZER_VERSION", "").strip()
    if _is_valid_semver(env_version):
        return env_version.split("+", 1)[0].split("-", 1)[0]

    git_version = _current_version_from_git()
    if git_version:
        return git_version

    return DEFAULT_VERSION


def _fetch_json(url: str, timeout: float):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AudioVisualizer-UpdateChecker",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_repo_web_url(remote_url: str) -> str:
    url = (remote_url or "").strip()
    if not url:
        return ""
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    return url


def _http_error_message(e: urllib.error.HTTPError) -> str:
    """Return a user-friendly HTTP error message for update checks."""
    code = getattr(e, "code", None)
    headers = getattr(e, "headers", {}) or {}

    # GitHub unauthenticated rate limit often appears as HTTP 403 with remaining=0.
    remaining = str(headers.get("X-RateLimit-Remaining", "")).strip()
    reset_raw = str(headers.get("X-RateLimit-Reset", "")).strip()
    retry_after_raw = str(headers.get("Retry-After", "")).strip()

    is_rate_limited = code == 429 or (code == 403 and remaining == "0")
    if not is_rate_limited:
        return f"GitHub API HTTP {code}"

    wait_seconds = None
    if retry_after_raw.isdigit():
        wait_seconds = int(retry_after_raw)
    elif reset_raw.isdigit():
        reset_ts = int(reset_raw)
        wait_seconds = max(0, reset_ts - int(time.time()))

    if wait_seconds is None:
        return "GitHub API rate limit reached. Please try again later."

    wait_minutes = max(1, int((wait_seconds + 59) / 60))
    return f"GitHub API rate limit reached. Try again in about {wait_minutes} minute(s)."


def _is_rate_limited_http_error(e: urllib.error.HTTPError) -> bool:
    code = getattr(e, "code", None)
    headers = getattr(e, "headers", {}) or {}
    remaining = str(headers.get("X-RateLimit-Remaining", "")).strip()
    return code == 429 or (code == 403 and remaining == "0")


def _select_installer_asset(assets: list[dict]) -> tuple[str, str]:
    """Return (url, name) for the installer exe asset if available."""
    if not isinstance(assets, list):
        return ("", "")

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if not INSTALLER_ASSET_REGEX.match(name):
            continue
        url = str(asset.get("browser_download_url") or "")
        if url:
            return (url, name)

    return ("", "")


def _latest_version_from_git_tags(timeout: float = 8.0):
    """Best-effort latest semver tag lookup using local git + origin remote."""
    base_dir = os.path.dirname(__file__)
    try:
        remote = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=base_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        ).stdout.strip()
        if not remote:
            return None

        tag_lines = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", remote],
            cwd=base_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        ).stdout.splitlines()

        tag_names: list[str] = []
        for line in tag_lines:
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            ref = parts[1]
            if not ref.startswith("refs/tags/"):
                continue
            tag_name = ref.split("refs/tags/", 1)[1]
            tag_names.append(tag_name)

        best_name = _select_highest_semver_tag(tag_names)
        best_ver = _parse_semver(best_name)
        if best_ver == (0, 0, 0):
            return None

        web_url = _normalize_repo_web_url(remote)
        return {
            "latest_version": ".".join(str(x) for x in best_ver),
            "release_name": best_name,
            "release_url": f"{web_url}/releases" if web_url else "",
            "release_notes": "",
            "installer_asset_url": "",
            "installer_asset_name": "",
        }
    except Exception:
        return None


def _latest_version_from_web_release(timeout: float = 6.0):
    """Best-effort latest release lookup via GitHub web redirect (non-API)."""
    try:
        req = urllib.request.Request(
            RELEASES_LATEST_WEB_URL,
            headers={"User-Agent": "AudioVisualizer-UpdateChecker"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = str(resp.geturl() or "")

        m = re.search(r"/releases/tag/([^/?#]+)", final_url)
        if not m:
            return None

        tag_name = urllib.parse.unquote(m.group(1))
        sem = _parse_semver(tag_name)
        if sem == (0, 0, 0):
            return None

        latest_version = ".".join(str(x) for x in sem)
        installer_asset_name = f"AudioVisualizer-Setup-{latest_version}.exe"
        installer_asset_url = (
            f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest/download/"
            f"{installer_asset_name}"
        )

        return {
            "latest_version": latest_version,
            "release_name": tag_name,
            "release_url": final_url,
            "release_notes": "",
            "installer_asset_url": installer_asset_url,
            "installer_asset_name": installer_asset_name,
        }
    except Exception:
        return None


def _latest_version_from_releases_api(timeout: float = 6.0):
    data = _fetch_json(RELEASES_URL, timeout)
    latest_raw = str(data.get("tag_name") or data.get("name") or "")
    latest_semver = _parse_semver(latest_raw)
    if latest_semver == (0, 0, 0):
        return None

    latest_version = ".".join(str(x) for x in latest_semver)
    installer_asset_url, installer_asset_name = _select_installer_asset(data.get("assets") or [])
    return {
        "latest_version": latest_version,
        "release_url": str(data.get("html_url") or ""),
        "release_name": str(data.get("name") or latest_raw or "Latest release"),
        "release_notes": str(data.get("body") or ""),
        "installer_asset_url": installer_asset_url,
        "installer_asset_name": installer_asset_name,
    }


def _latest_version_from_tags_api(timeout: float = 6.0):
    tags = _fetch_json(f"{TAGS_URL}?per_page=100", timeout)
    if not isinstance(tags, list) or not tags:
        return None

    tag_names = [str(tag.get("name") or "") for tag in tags]
    tag_name = _select_highest_semver_tag(tag_names)
    if not tag_name:
        return None

    latest_semver = _parse_semver(tag_name)
    if latest_semver == (0, 0, 0):
        return None

    return {
        "latest_version": ".".join(str(x) for x in latest_semver),
        "release_url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tag/{tag_name}",
        "release_name": tag_name or "Latest tag",
        "release_notes": "",
        "installer_asset_url": "",
        "installer_asset_name": "",
    }


def _build_error_result(current_version: str, message: str, status: str) -> dict:
    return {
        "ok": False,
        "status": status,
        "error": message,
        "current_version": current_version,
        "latest_version": "",
        "update_available": False,
        "release_url": "",
        "release_name": "",
        "release_notes": "",
        "installer_asset_url": "",
        "installer_asset_name": "",
    }


def _discover_latest_release(timeout: float) -> tuple[dict | None, str, str]:
    """Return (payload, error_status, error_message)."""
    attempt_errors: list[str] = []
    saw_rate_limit = False

    strategies = [
        _latest_version_from_releases_api,
        _latest_version_from_tags_api,
        lambda t: _latest_version_from_git_tags(timeout=max(8.0, t)),
        lambda t: _latest_version_from_web_release(timeout=max(6.0, t)),
    ]

    for strategy in strategies:
        try:
            payload = strategy(timeout)
            if payload:
                return payload, "", ""
        except urllib.error.HTTPError as e:
            if _is_rate_limited_http_error(e):
                saw_rate_limit = True
            attempt_errors.append(_http_error_message(e))
        except Exception as e:
            attempt_errors.append(str(e))

    if saw_rate_limit:
        return None, "error-rate-limited", "GitHub API rate limit reached. Please try again later."

    if attempt_errors:
        return None, "error-transient", attempt_errors[0]

    return None, "error-transient", "No releases or tags found"


def check_for_updates(timeout: float = 6.0) -> dict:
    """
    Check latest GitHub release and compare with current version.

    Returns:
      {
        "ok": bool,
        "status": str,
        "error": str,
        "current_version": str,
        "latest_version": str,
        "update_available": bool,
        "release_url": str,
        "release_name": str,
        "release_notes": str,
        "installer_asset_url": str,
        "installer_asset_name": str,
      }

    Status values:
      - "update-available"
      - "up-to-date"
      - "error-rate-limited"
      - "error-transient"
    """
    current_version = get_current_version()

    payload, error_status, error_message = _discover_latest_release(timeout)
    if not payload:
        return _build_error_result(current_version, error_message, error_status)

    latest_version = str(payload.get("latest_version") or "")
    release_url = str(payload.get("release_url") or "")
    release_name = str(payload.get("release_name") or "")
    release_notes = str(payload.get("release_notes") or "")
    installer_asset_url = str(payload.get("installer_asset_url") or "")
    installer_asset_name = str(payload.get("installer_asset_name") or "")

    current_semver = _parse_semver(current_version)
    latest_semver = _parse_semver(latest_version)
    update_available = latest_semver > current_semver

    return {
        "ok": True,
        "status": "update-available" if update_available else "up-to-date",
        "error": "",
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": update_available,
        "release_url": release_url,
        "release_name": release_name,
        "release_notes": release_notes,
        "installer_asset_url": installer_asset_url,
        "installer_asset_name": installer_asset_name,
    }
