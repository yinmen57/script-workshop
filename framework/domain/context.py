"""请求上下文：租户与身份（唯一可信来源）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AuthContext:
    tenant_id: str
    actor: str
    user_id: str | None = None
    permissions: list[str] = field(default_factory=list)
    auth_type: str = "jwt"  # jwt | api_key

    def require(self, permission: str) -> None:
        from framework.domain.errors import ForbiddenError

        if permission not in self.permissions:
            raise ForbiddenError(f"missing permission: {permission}")
