from __future__ import annotations

from app.auth.deps import get_current_user
from app.db import get_session
from app.domain.models import Group, Invitation, User
from app.domain.schemas import GroupCreateIn, GroupOut, InvitationOut, InviteIn
from app.groups import service
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(tags=["groups"])


@router.post("/groups", response_model=GroupOut, status_code=201)
def create_group(
        body: GroupCreateIn,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> GroupOut:
    group = service.create_group(session, user, body.name)
    return GroupOut(
        id=group.id, name=group.name, owner_id=group.owner_id, member_count=1, is_owner=True
    )


@router.get("/groups", response_model=list[GroupOut])
def list_groups(
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> list[GroupOut]:
    return [
        GroupOut(
            id=g.id, name=g.name, owner_id=g.owner_id, member_count=count, is_owner=is_owner
        )
        for g, count, is_owner in service.list_groups(session, user)
    ]


@router.post("/groups/{group_id}/invite", response_model=InvitationOut, status_code=201)
def invite_member(
        group_id: int,
        body: InviteIn,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> InvitationOut:
    group = session.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    if not service.is_member(session, group_id, user.id):
        raise HTTPException(status_code=403, detail="Only members can invite")
    inv = service.invite(session, group, user, body.email)
    return InvitationOut(
        id=inv.id,
        group_id=group.id,
        group_name=group.name,
        inviter_email=user.email,
        status=inv.status,
        created_at=inv.created_at,
    )


@router.get("/invitations", response_model=list[InvitationOut])
def my_invitations(
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> list[InvitationOut]:
    out: list[InvitationOut] = []
    for inv in service.list_invitations(session, user):
        group = session.get(Group, inv.group_id)
        inviter = session.get(User, inv.inviter_id)
        out.append(
            InvitationOut(
                id=inv.id,
                group_id=inv.group_id,
                group_name=group.name if group else "",
                inviter_email=inviter.email if inviter else "",
                status=inv.status,
                created_at=inv.created_at,
            )
        )
    return out


@router.post("/invitations/{invitation_id}/respond", status_code=204)
def respond_invitation(
        invitation_id: int,
        accept: bool,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> None:
    inv = session.get(Invitation, invitation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.invitee_email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="This invitation is not addressed to you")
    service.respond_invitation(session, inv, user, accept)
