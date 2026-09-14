"""Bitbucket git integration: clone / pull / push.

Credentials are never written to disk. `git.Repo.clone_from` does embed
the URL it was given into `.git/config`'s `origin` remote, so right after
cloning we rewrite that remote back to the plain (credential-free) URL.
For pull/push we never touch the stored remote at all — we pass the
authenticated URL as an explicit, one-off argument to `git pull`/`git
push`, so it's used in memory for a single subprocess call and never
persisted.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import git
from git import GitCommandError, Repo

_CRED_URL_RE = re.compile(r"https://[^/@\s]+:[^/@\s]+@")


@dataclass
class GitOpResult:
    ok: bool
    message: str


def _scrub(text: str) -> str:
    return _CRED_URL_RE.sub("https://***:***@", text)


def build_auth_url(repo_url: str, username: str, app_password: str) -> str:
    parts = urlsplit(repo_url)
    if parts.scheme not in ("http", "https"):
        raise ValueError("repo_url must be an http(s) URL for App Password auth")
    netloc = f"{quote(username, safe='')}:{quote(app_password, safe='')}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def is_cloned(dest_path: Path) -> bool:
    return (dest_path / ".git").exists()


def clone(repo_url: str, branch: str, dest_path: Path, username: str, app_password: str) -> GitOpResult:
    if is_cloned(dest_path):
        return GitOpResult(False, "이미 clone된 사이트입니다.")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        auth_url = build_auth_url(repo_url, username, app_password)
        Repo.clone_from(auth_url, dest_path, branch=branch)
        repo = Repo(dest_path)
        repo.remotes.origin.set_url(repo_url)  # scrub credentials from .git/config
        return GitOpResult(True, "clone 완료")
    except GitCommandError as exc:
        return GitOpResult(False, f"clone 실패: {_scrub(str(exc))}")
    except Exception as exc:  # noqa: BLE001
        return GitOpResult(False, f"clone 실패: {_scrub(str(exc))}")


def pull(repo_url: str, branch: str, dest_path: Path, username: str, app_password: str) -> GitOpResult:
    if not is_cloned(dest_path):
        return GitOpResult(False, "아직 clone되지 않은 사이트입니다. 먼저 clone하세요.")
    try:
        auth_url = build_auth_url(repo_url, username, app_password)
        repo = Repo(dest_path)
        repo.git.pull(auth_url, branch)
        return GitOpResult(True, "pull 완료")
    except GitCommandError as exc:
        return GitOpResult(False, f"pull 실패: {_scrub(str(exc))}")
    except Exception as exc:  # noqa: BLE001
        return GitOpResult(False, f"pull 실패: {_scrub(str(exc))}")


def push(
    repo_url: str,
    branch: str,
    dest_path: Path,
    username: str,
    app_password: str,
    commit_message: str = "",
) -> GitOpResult:
    if not is_cloned(dest_path):
        return GitOpResult(False, "아직 clone되지 않은 사이트입니다. 먼저 clone하세요.")
    try:
        auth_url = build_auth_url(repo_url, username, app_password)
        repo = Repo(dest_path)
        if repo.is_dirty(untracked_files=True):
            repo.git.add(A=True)
            repo.git.commit(m=commit_message or "Update via LTE-R VCS")
        repo.git.push(auth_url, f"{branch}:{branch}")
        return GitOpResult(True, "push 완료")
    except GitCommandError as exc:
        return GitOpResult(False, f"push 실패: {_scrub(str(exc))}")
    except Exception as exc:  # noqa: BLE001
        return GitOpResult(False, f"push 실패: {_scrub(str(exc))}")
