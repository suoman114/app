import re
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from server import git_ops
from server.config import REPOS_DIR
from server.db import get_session
from server.models import BitbucketConfig, Site

router = APIRouter(prefix="/api/sites", tags=["sites"])

_SLUG_RE = re.compile(r"[^a-zA-Z0-9-]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip()).strip("-").lower()
    return slug or "site"


def _unique_slug(session: Session, base_slug: str, exclude_id: Optional[int] = None) -> str:
    slug = base_slug
    n = 2
    while True:
        query = select(Site).where(Site.slug == slug)
        existing = session.exec(query).first()
        if existing is None or existing.id == exclude_id:
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


def _site_path(site: Site):
    return REPOS_DIR / site.slug


def _bitbucket_creds(session: Session) -> tuple[str, str]:
    config = session.exec(select(BitbucketConfig)).first()
    if config is None or not config.username or not config.app_password:
        raise HTTPException(400, "Bitbucket 인증 정보(사용자명/App Password)가 설정되지 않았습니다.")
    return config.username, config.app_password


class SiteIn(BaseModel):
    name: str
    repo_url: str
    branch: str = "main"
    description: str = ""


class SiteOut(BaseModel):
    id: int
    name: str
    repo_url: str
    branch: str
    slug: str
    description: str
    cloned: bool


class ActionResult(BaseModel):
    ok: bool
    message: str


class PushIn(BaseModel):
    commit_message: str = ""


def _to_out(site: Site) -> SiteOut:
    return SiteOut(
        id=site.id,
        name=site.name,
        repo_url=site.repo_url,
        branch=site.branch,
        slug=site.slug,
        description=site.description,
        cloned=git_ops.is_cloned(_site_path(site)),
    )


@router.get("", response_model=list[SiteOut])
def list_sites(session: Session = Depends(get_session)):
    sites = session.exec(select(Site).order_by(Site.name)).all()
    return [_to_out(s) for s in sites]


@router.post("", response_model=SiteOut)
def create_site(payload: SiteIn, session: Session = Depends(get_session)):
    if not payload.name.strip():
        raise HTTPException(400, "사이트 이름을 입력하세요.")
    if not payload.repo_url.strip():
        raise HTTPException(400, "저장소 URL을 입력하세요.")
    existing = session.exec(select(Site).where(Site.name == payload.name)).first()
    if existing is not None:
        raise HTTPException(400, "이미 존재하는 사이트 이름입니다.")

    slug = _unique_slug(session, _slugify(payload.name))
    site = Site(
        name=payload.name.strip(),
        repo_url=payload.repo_url.strip(),
        branch=(payload.branch or "main").strip(),
        slug=slug,
        description=payload.description.strip(),
    )
    session.add(site)
    session.commit()
    session.refresh(site)
    return _to_out(site)


@router.put("/{site_id}", response_model=SiteOut)
def update_site(site_id: int, payload: SiteIn, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    duplicate = session.exec(
        select(Site).where(Site.name == payload.name, Site.id != site_id)
    ).first()
    if duplicate is not None:
        raise HTTPException(400, "이미 존재하는 사이트 이름입니다.")

    site.name = payload.name.strip()
    site.repo_url = payload.repo_url.strip()
    site.branch = (payload.branch or "main").strip()
    site.description = payload.description.strip()
    session.add(site)
    session.commit()
    session.refresh(site)
    return _to_out(site)


@router.delete("/{site_id}", response_model=ActionResult)
def delete_site(site_id: int, delete_local: bool = False, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    if delete_local:
        path = _site_path(site)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    session.delete(site)
    session.commit()
    return ActionResult(ok=True, message="삭제되었습니다.")


@router.post("/{site_id}/clone", response_model=ActionResult)
def clone_site(site_id: int, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    username, app_password = _bitbucket_creds(session)
    result = git_ops.clone(site.repo_url, site.branch, _site_path(site), username, app_password)
    if result.ok:
        from datetime import datetime

        site.last_synced_at = datetime.utcnow()
        session.add(site)
        session.commit()
    return ActionResult(ok=result.ok, message=result.message)


@router.post("/{site_id}/pull", response_model=ActionResult)
def pull_site(site_id: int, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    username, app_password = _bitbucket_creds(session)
    result = git_ops.pull(site.repo_url, site.branch, _site_path(site), username, app_password)
    if result.ok:
        from datetime import datetime

        site.last_synced_at = datetime.utcnow()
        session.add(site)
        session.commit()
    return ActionResult(ok=result.ok, message=result.message)


@router.post("/{site_id}/push", response_model=ActionResult)
def push_site(site_id: int, payload: PushIn, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    username, app_password = _bitbucket_creds(session)
    result = git_ops.push(
        site.repo_url, site.branch, _site_path(site), username, app_password, payload.commit_message
    )
    if result.ok:
        from datetime import datetime

        site.last_synced_at = datetime.utcnow()
        session.add(site)
        session.commit()
    return ActionResult(ok=result.ok, message=result.message)
