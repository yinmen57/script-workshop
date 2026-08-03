"""FastAPI 依赖：会话、鉴权、请求 ID。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from framework.domain.context import AuthContext
from framework.domain.errors import UnauthorizedError
from framework.governance.auth_service import resolve_bearer
from framework.infra.db import get_session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


async def get_auth_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError("missing bearer token")
    auth = await resolve_bearer(session, token)
    request.state.auth = auth
    return auth


DbSession = Annotated[AsyncSession, Depends(get_db)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
RequestIdDep = Annotated[str, Depends(get_request_id)]
