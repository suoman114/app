from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from server.db import get_session
from server.models import BitbucketConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])


class BitbucketConfigOut(BaseModel):
    base_url: str
    username: str
    app_password_set: bool


class BitbucketConfigIn(BaseModel):
    base_url: str = ""
    username: str = ""
    app_password: str = ""


def _get_or_create(session: Session) -> BitbucketConfig:
    config = session.exec(select(BitbucketConfig)).first()
    if config is None:
        config = BitbucketConfig()
        session.add(config)
        session.commit()
        session.refresh(config)
    return config


@router.get("/bitbucket", response_model=BitbucketConfigOut)
def get_bitbucket_config(session: Session = Depends(get_session)):
    config = _get_or_create(session)
    return BitbucketConfigOut(
        base_url=config.base_url,
        username=config.username,
        app_password_set=bool(config.app_password),
    )


@router.put("/bitbucket", response_model=BitbucketConfigOut)
def update_bitbucket_config(payload: BitbucketConfigIn, session: Session = Depends(get_session)):
    config = _get_or_create(session)
    config.base_url = payload.base_url
    config.username = payload.username
    if payload.app_password:
        # blank app_password in the request means "keep the existing one"
        config.app_password = payload.app_password
    session.add(config)
    session.commit()
    session.refresh(config)
    return BitbucketConfigOut(
        base_url=config.base_url,
        username=config.username,
        app_password_set=bool(config.app_password),
    )
