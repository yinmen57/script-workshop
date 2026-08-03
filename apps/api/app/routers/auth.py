"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.deps import AuthDep, DbSession, RequestIdDep
from app.schemas import LoginRequest, MeResponse, TokenResponse
from framework.governance.audit import write_audit
from framework.governance.auth_service import get_me, login
from framework.governance.security import create_access_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def auth_login(
    body: LoginRequest,
    session: DbSession,
    request: Request,
    request_id: RequestIdDep,
) -> TokenResponse:
    result = await login(session, body.account, body.password)
    # 登录审计（tenant 从 token 解码前先查用户，这里用结果后补充）
    payload = decode_token(result["access_token"])
    await write_audit(
        session,
        tenant_id=payload["tenant_id"],
        actor=payload["sub"],
        action="auth.login",
        request_id=request_id,
        ip=request.client.host if request.client else None,
    )
    return TokenResponse(**result)


@router.post("/refresh", response_model=TokenResponse)
async def auth_refresh(body: dict, session: DbSession) -> TokenResponse:
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        from framework.domain.errors import ValidationAppError

        raise ValidationAppError("refresh_token required")
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        from framework.domain.errors import UnauthorizedError

        raise UnauthorizedError("invalid refresh token")

    from framework.governance.auth_service import load_permissions
    from framework.governance.security import create_refresh_token

    permissions = await load_permissions(session, payload["sub"])
    access = create_access_token(
        user_id=payload["sub"],
        tenant_id=payload["tenant_id"],
        permissions=permissions,
    )
    new_refresh = create_refresh_token(
        user_id=payload["sub"],
        tenant_id=payload["tenant_id"],
    )
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=7200,
    )


@router.post("/logout")
async def auth_logout(auth: AuthDep, request_id: RequestIdDep, session: DbSession) -> dict:
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="auth.logout",
        request_id=request_id,
    )
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def auth_me(auth: AuthDep, session: DbSession) -> MeResponse:
    data = await get_me(session, auth)
    return MeResponse(**data)
