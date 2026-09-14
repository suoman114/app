"""Browse, edit, and upload files inside a site's cloned working copy.

All paths are relative to the site's clone directory (data/repos/<slug>)
and are resolved+validated against that root before any filesystem
access, so a crafted `path` (e.g. `../../etc/passwd`) can never escape
the site's own clone.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from server import git_ops
from server.config import REPOS_DIR
from server.db import get_session
from server.models import Site

router = APIRouter(prefix="/api/sites", tags=["files"])

MAX_EDIT_FILE_SIZE = 2 * 1024 * 1024  # 2 MiB — sane cap for a textarea editor
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MiB


def _site_path(site: Site) -> Path:
    return REPOS_DIR / site.slug


def _get_site(site_id: int, session: Session) -> Site:
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    if not git_ops.is_cloned(_site_path(site)):
        raise HTTPException(400, "먼저 clone하세요.")
    return site


def _resolve_safe_path(site: Site, rel_path: str) -> Path:
    root = _site_path(site).resolve()
    rel_path = (rel_path or "").strip().lstrip("/")
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(400, "잘못된 경로입니다.")
    return candidate


class FileEntry(BaseModel):
    name: str
    type: str  # "dir" | "file"
    size: int
    modified: str


class FileListOut(BaseModel):
    path: str
    entries: list[FileEntry]


class FileContentOut(BaseModel):
    path: str
    content: str
    binary: bool


class FileSaveIn(BaseModel):
    path: str
    content: str


class ActionResult(BaseModel):
    ok: bool
    message: str


@router.get("/{site_id}/files", response_model=FileListOut)
def list_files(site_id: int, path: str = "", session: Session = Depends(get_session)):
    site = _get_site(site_id, session)
    target = _resolve_safe_path(site, path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "디렉토리를 찾을 수 없습니다.")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if child.name == ".git":
            continue
        stat = child.stat()
        entries.append(
            FileEntry(
                name=child.name,
                type="dir" if child.is_dir() else "file",
                size=0 if child.is_dir() else stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            )
        )
    return FileListOut(path=path.strip("/"), entries=entries)


@router.get("/{site_id}/files/content", response_model=FileContentOut)
def get_file_content(site_id: int, path: str, session: Session = Depends(get_session)):
    site = _get_site(site_id, session)
    target = _resolve_safe_path(site, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    if target.stat().st_size > MAX_EDIT_FILE_SIZE:
        raise HTTPException(400, "파일이 너무 커서 편집할 수 없습니다 (2MB 초과).")
    raw = target.read_bytes()
    try:
        return FileContentOut(path=path, content=raw.decode("utf-8"), binary=False)
    except UnicodeDecodeError:
        return FileContentOut(path=path, content="", binary=True)


@router.put("/{site_id}/files/content", response_model=ActionResult)
def save_file_content(site_id: int, payload: FileSaveIn, session: Session = Depends(get_session)):
    site = _get_site(site_id, session)
    target = _resolve_safe_path(site, payload.path)
    if target.is_dir():
        raise HTTPException(400, "디렉토리에는 저장할 수 없습니다.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return ActionResult(ok=True, message="저장되었습니다.")


@router.post("/{site_id}/files/upload", response_model=ActionResult)
async def upload_file(
    site_id: int,
    path: str = Form(""),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    site = _get_site(site_id, session)
    dir_target = _resolve_safe_path(site, path)
    if not dir_target.exists() or not dir_target.is_dir():
        raise HTTPException(400, "대상 디렉토리를 찾을 수 없습니다.")

    safe_name = Path(file.filename or "").name
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(400, "잘못된 파일명입니다.")
    dest = dir_target / safe_name
    dest.relative_to(_site_path(site).resolve())  # belt-and-suspenders vs a crafted filename

    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    raise HTTPException(400, "파일이 너무 큽니다 (50MB 초과).")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    return ActionResult(ok=True, message=f"업로드 완료: {safe_name}")
