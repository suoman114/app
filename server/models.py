from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Site(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    repo_url: str
    branch: str = Field(default="main")
    slug: str = Field(unique=True, index=True)
    description: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_synced_at: Optional[datetime] = None


class BitbucketConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    base_url: str = Field(default="")
    username: str = Field(default="")
    app_password: str = Field(default="")
