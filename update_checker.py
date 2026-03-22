"""
update_checker.py - Lightweight app update checks via GitHub Releases API.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request


GITHUB_OWNER = "DeKairos"
GITHUB_REPO = "Taskbar_Audio-_Visualizer"
DEFAULT_VERSION = "0.0.0"
RELEASES_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
TAGS_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/tags"


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
        }
    except Exception:
        return None


def check_for_updates(timeout: float = 6.0) -> dict:
    """
    Check latest GitHub release and compare with current version.

    Returns:
      {
        "ok": bool,
        "error": str,
        "current_version": str,
        "latest_version": str,
        "update_available": bool,
        "release_url": str,
        "release_name": str,
      }
    """
    current_version = get_current_version()

    latest_version = ""
    release_url = ""
    release_name = ""
    try:
        data = _fetch_json(RELEASES_URL, timeout)
        latest_raw = str(data.get("tag_name") or data.get("name") or "")
        latest_semver = _parse_semver(latest_raw)
        latest_version = ".".join(str(x) for x in latest_semver)
        release_url = str(data.get("html_url") or "")
        release_name = str(data.get("name") or latest_raw or "Latest release")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return {
                "ok": False,
                "error": f"GitHub API HTTP {e.code}",
                "current_version": current_version,
                "latest_version": "",
                "update_available": False,
                "release_url": "",
                "release_name": "",
            }
        # Some repositories don't publish releases; fall back to latest tag.
        try:
            tags = _fetch_json(f"{TAGS_URL}?per_page=100", timeout)
            if not isinstance(tags, list) or not tags:
                return {
                    "ok": False,
                    "error": "No releases or tags found",
                    "current_version": current_version,
                    "latest_version": "",
                    "update_available": False,
                    "release_url": "",
                    "release_name": "",
                }
            tag_names = [str(tag.get("name") or "") for tag in tags]
            tag_name = _select_highest_semver_tag(tag_names)
            if not tag_name:
                return {
                    "ok": False,
                    "error": "No semver tags found",
                    "current_version": current_version,
                    "latest_version": "",
                    "update_available": False,
                    "release_url": "",
                    "release_name": "",
                }
            latest_semver = _parse_semver(tag_name)
            latest_version = ".".join(str(x) for x in latest_semver)
            release_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tag/{tag_name}"
            release_name = tag_name or "Latest tag"
        except Exception:
            git_fallback = _latest_version_from_git_tags(timeout=max(8.0, timeout))
            if not git_fallback:
                return {
                    "ok": False,
                    "error": "No releases or tags found",
                    "current_version": current_version,
                    "latest_version": "",
                    "update_available": False,
                    "release_url": "",
                    "release_name": "",
                }
            latest_version = git_fallback["latest_version"]
            release_url = git_fallback["release_url"]
            release_name = git_fallback["release_name"]
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "current_version": current_version,
            "latest_version": "",
            "update_available": False,
            "release_url": "",
            "release_name": "",
        }

    current_semver = _parse_semver(current_version)
    latest_semver = _parse_semver(latest_version)

    return {
        "ok": True,
        "error": "",
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": latest_semver > current_semver,
        "release_url": release_url,
        "release_name": release_name,
    }
