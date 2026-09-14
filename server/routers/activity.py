from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from server.db import get_session
from server.models import ActivityLog

router = APIRouter(prefix="/api/activity", tags=["activity"])


class ActivityLogOut(BaseModel):
    id: int
    site_id: int | None
    site_name: str
    action: str
    ok: bool
    message: str
    created_at: str


@router.get("", response_model=list[ActivityLogOut])
def list_activity(limit: int = 50, session: Session = Depends(get_session)):
    logs = session.exec(
        select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(min(limit, 200))
    ).all()
    return [
        ActivityLogOut(
            id=log.id,
            site_id=log.site_id,
            site_name=log.site_name,
            action=log.action,
            ok=log.ok,
            message=log.message,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]
