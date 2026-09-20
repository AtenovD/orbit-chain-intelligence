"""Optional, no-op-safe Sentry bootstrap for production error visibility."""
from __future__ import annotations

import logging

from orchestrator.config import get_settings

logger = logging.getLogger("orbit.observability")


def configure_sentry(app) -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        integrations=[FastApiIntegration()],
        send_default_pii=False,
        traces_sample_rate=0.05,
    )
