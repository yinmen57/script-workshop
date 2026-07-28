"""认证服务：登录、当前用户、API Key。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.context import AuthContext
from packages.domain.errors import UnauthorizedError
from packages.governance.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_api_key,
    verify_password,
)
from packages.infra.config import get_settings


async def login(session: AsyncSession, account: str, password: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT u.id, u.tenant_id, u.password_hash, u.status, u.display_name
                FROM user_account u
                WHERE u.account = :account AND u.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"account": account},
        )
    ).mappings().first()
    if row is None:
        raise UnauthorizedError("invalid account or password")
    # 本地开发：不校验密码，账号存在且 active 即可登录
    if get_settings().app_env != "dev":
        if not verify_password(password, row["password_hash"]):
            raise UnauthorizedError("invalid account or password")
    if row["status"] != "active":
        raise UnauthorizedError("user suspended")

    permissions = await load_permissions(session, row["id"])
    access = create_access_token(
        user_id=row["id"],
        tenant_id=row["tenant_id"],
        permissions=permissions,
    )
    refresh = create_refresh_token(user_id=row["id"], tenant_id=row["tenant_id"])
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 7200,
        "token_type": "bearer",
    }


async def get_me(session: AsyncSession, auth: AuthContext) -> dict:
    if not auth.user_id:
        return {
            "user_id": None,
            "display_name": auth.actor,
            "tenant_id": auth.tenant_id,
            "permissions": auth.permissions,
        }
    row = (
        await session.execute(
            text(
                """
                SELECT id, display_name, tenant_id
                FROM user_account
                WHERE id = :user_id AND deleted_at IS NULL
                """
            ),
            {"user_id": auth.user_id},
        )
    ).mappings().first()
    if row is None:
        raise UnauthorizedError("user not found")
    return {
        "user_id": row["id"],
        "display_name": row["display_name"],
        "tenant_id": row["tenant_id"],
        "permissions": auth.permissions,
    }


async def resolve_bearer(session: AsyncSession, token: str) -> AuthContext:
    # API Key：sk_ 前缀
    if token.startswith("sk_"):
        return await _resolve_api_key(session, token)

    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedError("invalid access token")
    return AuthContext(
        tenant_id=payload["tenant_id"],
        user_id=payload["sub"],
        actor=payload["sub"],
        permissions=list(payload.get("permissions") or []),
        auth_type="jwt",
    )


async def _resolve_api_key(session: AsyncSession, raw_key: str) -> AuthContext:
    key_hash = hash_api_key(raw_key)
    row = (
        await session.execute(
            text(
                """
                SELECT id, tenant_id, scopes, status, expires_at
                FROM api_credential
                WHERE key_hash = :key_hash
                LIMIT 1
                """
            ),
            {"key_hash": key_hash},
        )
    ).mappings().first()
    if row is None or row["status"] != "active":
        raise UnauthorizedError("invalid api key")

    scopes = row["scopes"]
    if isinstance(scopes, str):
        import json

        scopes = json.loads(scopes)
    return AuthContext(
        tenant_id=row["tenant_id"],
        actor=f"api_key:{row['id']}",
        user_id=None,
        permissions=list(scopes or []),
        auth_type="api_key",
    )


async def load_permissions(session: AsyncSession, user_id: str) -> list[str]:
    import json

    rows = (
        await session.execute(
            text(
                """
                SELECT r.permissions
                FROM user_role ur
                JOIN role r ON r.id = ur.role_id
                WHERE ur.user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    result: set[str] = set()
    for row in rows:
        perms = row["permissions"]
        if isinstance(perms, str):
            perms = json.loads(perms)
        result.update(perms or [])
    return sorted(result)
