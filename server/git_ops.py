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


@dataclass
class SiteStatus:
    cloned: bool
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    last_commit_message: str = ""
    last_commit_date: str = ""
    error: str = ""


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
        # We pushed to an explicit URL rather than the configured "origin"
        # remote, so git does not auto-update the local origin/<branch>
        # tracking ref. Do it ourselves so status() reflects the push
        # immediately instead of showing a stale "ahead" count.
        repo.git.update_ref(f"refs/remotes/origin/{branch}", repo.head.commit.hexsha)
        return GitOpResult(True, "push 완료")
    except GitCommandError as exc:
        return GitOpResult(False, f"push 실패: {_scrub(str(exc))}")
    except Exception as exc:  # noqa: BLE001
        return GitOpResult(False, f"push 실패: {_scrub(str(exc))}")


def status(branch: str, dest_path: Path) -> SiteStatus:
    """Local-only status: dirty/ahead/behind as of the last clone/pull/push.

    Deliberately does not fetch from the remote (that would need
    credentials and a network round trip on every site-list load) — call
    `pull` to refresh what "behind" means.
    """
    if not is_cloned(dest_path):
        return SiteStatus(cloned=False)
    try:
        repo = Repo(dest_path)
        dirty = repo.is_dirty(untracked_files=True)
        ahead = behind = 0
        remote_ref = f"origin/{branch}"
        if remote_ref in [str(r) for r in repo.refs]:
            ahead = sum(1 for _ in repo.iter_commits(f"{remote_ref}..{branch}"))
            behind = sum(1 for _ in repo.iter_commits(f"{branch}..{remote_ref}"))
        last_commit_message = ""
        last_commit_date = ""
        if repo.head.is_valid():
            head_commit = repo.head.commit
            last_commit_message = head_commit.message.strip().splitlines()[0]
            last_commit_date = head_commit.committed_datetime.isoformat()
        return SiteStatus(
            cloned=True,
            dirty=dirty,
            ahead=ahead,
            behind=behind,
            last_commit_message=last_commit_message,
            last_commit_date=last_commit_date,
        )
    except Exception as exc:  # noqa: BLE001
        return SiteStatus(cloned=True, error=_scrub(str(exc)))
