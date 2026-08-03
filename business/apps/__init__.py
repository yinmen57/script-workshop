"""业务 Agent 应用插件；框架通过 register_business_apps 注入。"""

from business.apps.bootstrap import register_business_apps

__all__ = ["register_business_apps"]
