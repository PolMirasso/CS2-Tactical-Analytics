from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import InviteStatus
from app.domain.models import Group, GroupMembership, Invitation, User


def create_group(session: Session, owner: User, name: str) -> Group:
    group = Group(name=name, owner_id=owner.id)
    session.add(group)
    session.flush()
    session.add(GroupMembership(group_id=group.id, user_id=owner.id))
    session.flush()
    return group


def _member_group_ids(session: Session, user_id: int) -> list[int]:
    return list(
        session.scalars(
            select(GroupMembership.group_id).where(GroupMembership.user_id == user_id)
        )
    )


def is_member(session: Session, group_id: int, user_id: int) -> bool:
    return (
            session.scalar(
                select(GroupMembership.id).where(
                    GroupMembership.group_id == group_id,
                    GroupMembership.user_id == user_id,
                )
            )
            is not None
    )


def list_groups(session: Session, user: User) -> list[tuple[Group, int, bool]]:
    # Groups the user belongs to, with (group, member_count, is_owner)
    gids = _member_group_ids(session, user.id)
    out: list[tuple[Group, int, bool]] = []
    for gid in gids:
        group = session.get(Group, gid)
        if group is None:
            continue
        member_count = len(
            list(session.scalars(select(GroupMembership.id).where(GroupMembership.group_id == gid)))
        )
        out.append((group, member_count, group.owner_id == user.id))
    return out


def invite(session: Session, group: Group, inviter: User, email: str) -> Invitation:
    inv = Invitation(
        group_id=group.id,
        inviter_id=inviter.id,
        invitee_email=email.lower(),
        status=str(InviteStatus.PENDING),
    )
    session.add(inv)
    session.flush()
    return inv


def list_invitations(session: Session, user: User) -> list[Invitation]:
    return list(
        session.scalars(
            select(Invitation).where(
                Invitation.invitee_email == user.email.lower(),
                Invitation.status == str(InviteStatus.PENDING),
            )
        )
    )


def respond_invitation(session: Session, invitation: Invitation, user: User, accept: bool) -> None:
    invitation.status = str(InviteStatus.ACCEPTED if accept else InviteStatus.DECLINED)
    if accept and not is_member(session, invitation.group_id, user.id):
        session.add(GroupMembership(group_id=invitation.group_id, user_id=user.id))
    session.flush()


def group_peer_ids(session: Session, user_id: int) -> set[int]:
    # User ids that share at least one group with user_id
    gids = _member_group_ids(session, user_id)
    if not gids:
        return set()
    peers = set(
        session.scalars(
            select(GroupMembership.user_id).where(GroupMembership.group_id.in_(gids))
        )
    )
    peers.discard(user_id)
    return peers
