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
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit

import git
from git import GitCommandError, RemoteProgress, Repo

_CRED_URL_RE = re.compile(r"https://[^/@\s]+:[^/@\s]+@")
_PERCENT_RE = re.compile(r"(\d+)%")


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


@dataclass
class ProgressState:
    action: str = ""
    message: str = ""
    percent: Optional[float] = None
    running: bool = False
    ok: Optional[bool] = None


# In-memory clone/pull/push progress per site, polled by the frontend via
# GET /api/sites/{id}/progress while a POST /clone|pull|push is in flight
# on that same site (in a different worker thread).
_progress: dict[int, ProgressState] = {}
_progress_lock = threading.Lock()


def _set_progress(site_id: int, **fields) -> None:
    with _progress_lock:
        state = _progress.get(site_id, ProgressState())
        for key, value in fields.items():
            setattr(state, key, value)
        _progress[site_id] = state


def get_progress(site_id: int) -> ProgressState:
    with _progress_lock:
        return _progress.get(site_id, ProgressState())


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


class _CloneProgress(RemoteProgress):
    """Feeds GitPython's built-in clone progress parsing into _progress."""

    def __init__(self, site_id: int):
        super().__init__()
        self.site_id = site_id

    def update(self, op_code, cur_count, max_count=None, message=""):
        percent = None
        if max_count:
            try:
                percent = round(cur_count / float(max_count) * 100, 1)
            except (TypeError, ZeroDivisionError):
                percent = None
        _set_progress(
            self.site_id,
            message=_scrub((self._cur_line or message or "").strip()),
            percent=percent,
            running=True,
        )


def _run_git_streaming(dest_path: Path, args: list[str], site_id: int) -> None:
    """Run a git subprocess, feeding its --progress stderr into _progress.

    Used for pull/push, which (unlike clone) we invoke as an explicit CLI
    call rather than through GitPython's Remote object — see module
    docstring for why. Git writes progress as \\r-terminated lines to
    stderr, so we read the stream a line at a time (splitting on both
    \\r and \\n) instead of waiting for the process to exit.
    """
    proc = subprocess.Popen(
        ["git", "-C", str(dest_path)] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    last_line = ""
    buf = ""
    assert proc.stdout is not None
    while True:
        ch = proc.stdout.read(1)
        if ch == "":
            break
        if ch in ("\r", "\n"):
            if buf.strip():
                last_line = buf.strip()
                percent_match = _PERCENT_RE.search(last_line)
                _set_progress(
                    site_id,
                    message=_scrub(last_line),
                    percent=float(percent_match.group(1)) if percent_match else None,
                    running=True,
                )
            buf = ""
        else:
            buf += ch
    if buf.strip():
        last_line = buf.strip()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:1])} failed: {last_line}")


def clone(site_id: int, repo_url: str, branch: str, dest_path: Path, username: str, app_password: str) -> GitOpResult:
    if is_cloned(dest_path):
        return GitOpResult(False, "이미 clone된 사이트입니다.")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    _set_progress(site_id, action="clone", message="준비 중...", percent=0.0, running=True, ok=None)
    try:
        auth_url = build_auth_url(repo_url, username, app_password)
        Repo.clone_from(auth_url, dest_path, branch=branch, progress=_CloneProgress(site_id))
        repo = Repo(dest_path)
        repo.remotes.origin.set_url(repo_url)  # scrub credentials from .git/config
        _set_progress(site_id, message="완료", percent=100.0, running=False, ok=True)
        return GitOpResult(True, "clone 완료")
    except GitCommandError as exc:
        _set_progress(site_id, message="실패", running=False, ok=False)
        return GitOpResult(False, f"clone 실패: {_scrub(str(exc))}")
    except Exception as exc:  # noqa: BLE001
        _set_progress(site_id, message="실패", running=False, ok=False)
        return GitOpResult(False, f"clone 실패: {_scrub(str(exc))}")


def pull(site_id: int, repo_url: str, branch: str, dest_path: Path, username: str, app_password: str) -> GitOpResult:
    if not is_cloned(dest_path):
        return GitOpResult(False, "아직 clone되지 않은 사이트입니다. 먼저 clone하세요.")
    _set_progress(site_id, action="pull", message="준비 중...", percent=0.0, running=True, ok=None)
    try:
        auth_url = build_auth_url(repo_url, username, app_password)
        _run_git_streaming(dest_path, ["pull", "--progress", auth_url, branch], site_id)
        _set_progress(site_id, message="완료", percent=100.0, running=False, ok=True)
        return GitOpResult(True, "pull 완료")
    except GitCommandError as exc:
        _set_progress(site_id, message="실패", running=False, ok=False)
        return GitOpResult(False, f"pull 실패: {_scrub(str(exc))}")
    except Exception as exc:  # noqa: BLE001
        _set_progress(site_id, message="실패", running=False, ok=False)
        return GitOpResult(False, f"pull 실패: {_scrub(str(exc))}")


def push(
    site_id: int,
    repo_url: str,
    branch: str,
    dest_path: Path,
    username: str,
    app_password: str,
    commit_message: str = "",
) -> GitOpResult:
    if not is_cloned(dest_path):
        return GitOpResult(False, "아직 clone되지 않은 사이트입니다. 먼저 clone하세요.")
    _set_progress(site_id, action="push", message="준비 중...", percent=0.0, running=True, ok=None)
    try:
        auth_url = build_auth_url(repo_url, username, app_password)
        repo = Repo(dest_path)
        if repo.is_dirty(untracked_files=True):
            _set_progress(site_id, message="변경사항 커밋 중...", running=True)
            repo.git.add(A=True)
            repo.git.commit(m=commit_message or "Update via LTE-R VCS")
        _run_git_streaming(dest_path, ["push", "--progress", auth_url, f"{branch}:{branch}"], site_id)
        # We pushed to an explicit URL rather than the configured "origin"
        # remote, so git does not auto-update the local origin/<branch>
        # tracking ref. Do it ourselves so status() reflects the push
        # immediately instead of showing a stale "ahead" count.
        repo.git.update_ref(f"refs/remotes/origin/{branch}", repo.head.commit.hexsha)
        _set_progress(site_id, message="완료", percent=100.0, running=False, ok=True)
        return GitOpResult(True, "push 완료")
    except GitCommandError as exc:
        _set_progress(site_id, message="실패", running=False, ok=False)
        return GitOpResult(False, f"push 실패: {_scrub(str(exc))}")
    except Exception as exc:  # noqa: BLE001
        _set_progress(site_id, message="실패", running=False, ok=False)
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
