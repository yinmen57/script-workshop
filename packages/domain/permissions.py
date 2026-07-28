"""P0 权限点。"""

from __future__ import annotations

MODEL_READ = "model:read"
MODEL_WRITE = "model:write"
KB_READ = "kb:read"
KB_WRITE = "kb:write"
APP_READ = "app:read"
APP_WRITE = "app:write"
AUDIT_READ = "audit:read"

P0_PERMISSIONS = {
    MODEL_READ,
    MODEL_WRITE,
    KB_READ,
    KB_WRITE,
    APP_READ,
    APP_WRITE,
    AUDIT_READ,
}
