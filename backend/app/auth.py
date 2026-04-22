from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.errors import ApiError
from app.settings import Settings, get_settings

security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class AuthUser(BaseModel):
    user_id: str


def _decode_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
        )
    except jwt.PyJWTError:
        raise ApiError(
            status_code=401,
            code="AUTH_INVALID_TOKEN",
            message="invalid or expired token",
            retryable=False,
        )


def issue_access_token(user_id: str, settings: Settings) -> LoginResponse:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.auth_access_token_expire_min)
    payload = {
        "sub": user_id,
        "exp": expires_at,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)
    return LoginResponse(access_token=token, expires_at=expires_at)


def authenticate_demo_user(payload: LoginRequest, settings: Settings) -> LoginResponse:
    if payload.username != settings.auth_demo_user or payload.password != settings.auth_demo_password:
        raise ApiError(
            status_code=401,
            code="AUTH_INVALID_CREDENTIALS",
            message="invalid credentials",
            retryable=False,
        )
    return issue_access_token(user_id=payload.username, settings=settings)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(
            status_code=401,
            code="AUTH_TOKEN_REQUIRED",
            message="bearer token is required",
            retryable=False,
        )
    payload = _decode_token(credentials.credentials, settings)
    user_id = payload.get("sub")
    if not user_id:
        raise ApiError(
            status_code=401,
            code="AUTH_TOKEN_SUBJECT_MISSING",
            message="token subject is missing",
            retryable=False,
        )
    return AuthUser(user_id=user_id)
