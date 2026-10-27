from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from atlas.database import Base, get_session


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="workspace_name_not_blank"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


router = APIRouter(prefix="/workspaces", tags=["workspaces"])
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.post("", response_model=WorkspaceResponse, status_code=201)
def create_workspace(body: WorkspaceCreate, session: DatabaseSession) -> Workspace:
    workspace = Workspace(name=body.name)
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: UUID, session: DatabaseSession) -> Workspace:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace
