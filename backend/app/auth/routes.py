from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db import get_session
from app.domain.enums import Role
from app.domain.models import User
from app.domain.schemas import RegisterIn, Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, session: Session = Depends(get_session)) -> User:
    email = body.email.lower()
    exists = session.scalar(select(User).where(func.lower(User.email) == email))
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        role=str(Role.USER),
    )
    session.add(user)
    session.flush()
    return user


@router.post("/login", response_model=Token)
def login(
        form: OAuth2PasswordRequestForm = Depends(),
        session: Session = Depends(get_session),
) -> Token:
    # OAuth2 form uses `username`; we treat it as the email.
    user = session.scalar(select(User).where(func.lower(User.email) == form.username.lower()))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
