from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import secrets
import time
from typing import Any

from sqlalchemy import select

from orchestrator.config import get_settings
from orchestrator.context_connectors import connector_memory_markdown, connector_preset, fetch_context_connector
from orchestrator.context_oauth import configure_drive_watch, refresh_google, stop_drive_watch
from orchestrator.db import SessionFactory
from orchestrator.memory import index_memory_note
from orchestrator.models import MemoryNote, ProviderConnection
from orchestrator.security import secret_codec


logger = logging.getLogger("orbit.context_sync")


def _credentials(connection: ProviderConnection) -> dict[str, Any]:
    raw = secret_codec.decrypt(connection.api_key) or ""
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and value.get("access_token"):
            return value
    except json.JSONDecodeError:
        pass
    return {"access_token": raw}


async def _usable_credentials(connection: ProviderConnection) -> dict[str, Any]:
    credentials = _credentials(connection)
    connector = connection.provider.removeprefix("connector-")
    expires_at = credentials.get("expires_at")
    expired = False
    if expires_at:
        try:
            expired = datetime.fromisoformat(str(expires_at)).astimezone(timezone.utc) <= datetime.now(timezone.utc)
        except ValueError:
            expired = True
    if connector in {"google-drive", "youtube"} and expired and credentials.get("refresh_token"):
        refreshed = await refresh_google(str(credentials["refresh_token"]))
        credentials.update(refreshed)
        connection.api_key = secret_codec.encrypt(json.dumps(credentials, separators=(",", ":")))
    return credentials


def _replace_or_merge(content: str, connector: str, source: str, incremental: bool) -> str:
    start = f"<!-- source:connector-{connector} -->"
    end = f"<!-- /source:connector-{connector} -->"
    if start not in content or end not in content:
        return f"{content.rstrip()}\n\n{source}"
    prefix, remainder = content.split(start, 1)
    old, suffix = remainder.split(end, 1)
    if incremental and "\n### " in source:
        additions = "\n### " + source.split("\n### ", 1)[1].rsplit(end, 1)[0]
        merged = (old.rstrip() + additions)[-120_000:]
        source = f"{start}{merged}\n{end}"
    return f"{prefix.rstrip()}\n\n{source}{suffix}"


async def sync_context_connection(session, connection: ProviderConnection, *, reason: str = "manual") -> tuple[dict[str, Any], MemoryNote]:
    connector = connection.provider.removeprefix("connector-")
    preset = connector_preset(connector)
    credentials = await _usable_credentials(connection)
    config = dict(connection.config or {})
    token = str(credentials.get("access_token") or "")
    if not token and preset.get("credential_required", True):
        raise ValueError(f"{preset['name']} has no usable credential")
    result = await fetch_context_connector(
        connector,
        token,
        str(config.get("identifier") or "") or None,
        cursor=config.get("sync_cursor"),
        oauth=config.get("auth_method") == "oauth2",
    )
    if connector == "google-drive" and config.get("auth_method") == "oauth2" and get_settings().public_url.startswith("https://"):
        watch = dict(config.get("drive_watch") or {})
        if int(watch.get("expiration") or 0) <= int((time.time() + 24 * 60 * 60) * 1000):
            if watch.get("channel_id") and watch.get("resource_id"):
                try:
                    await stop_drive_watch(token, str(watch["channel_id"]), str(watch["resource_id"]))
                except Exception:
                    logger.warning("drive_watch_stop_failed connection=%s", connection.id)
            channel_token = secrets.token_urlsafe(32)
            webhook_url = f"{get_settings().public_url.rstrip('/')}{get_settings().api_prefix}/integrations/context/webhooks/google-drive/{connection.id}"
            watch = await configure_drive_watch(token, webhook_url, channel_token)
            watch["channel_token_hash"] = hashlib.sha256(channel_token.encode()).hexdigest()
            watch["webhook_url"] = webhook_url
            config["drive_watch"] = watch
    now = datetime.now(timezone.utc).isoformat()
    connection.name = f"{preset['name']} · {result['label']}"
    connection.enabled = True
    connection.config = {
        **config,
        "label": result["label"],
        "item_count": int(result.get("item_count", 0)),
        "content_bytes": int(result.get("content_bytes", 0)),
        "summary": result["summary"],
        "details": result.get("details", {}),
        "sync_cursor": result.get("cursor"),
        "has_more": bool(result.get("has_more")),
        "sync_status": "ready",
        "last_sync_reason": reason,
        "synced_at": now,
        "last_error": None,
    }
    memory = await session.scalar(select(MemoryNote).where(MemoryNote.workspace_id == connection.workspace_id, MemoryNote.scope == "global"))
    source = connector_memory_markdown(connector, result)
    if not memory:
        memory = MemoryNote(workspace_id=connection.workspace_id, scope="global", title="Main memory", summary="Long-term user context and connected knowledge sources.", content=f"# Main memory\n\n{source}")
        session.add(memory)
    else:
        memory.content = _replace_or_merge(memory.content, connector, source, connector in {"slack", "telegram"})
        memory.summary = f"Synced {preset['name']}: {result['label']}"
    memory.byte_size = len((memory.content + memory.summary).encode("utf-8"))
    await session.flush()
    await index_memory_note(session, memory)
    await session.commit()
    await session.refresh(connection)
    await session.refresh(memory)
    return result, memory


async def mark_sync_error(session, connection: ProviderConnection, error: Exception) -> None:
    connection.config = {**dict(connection.config or {}), "sync_status": "error", "last_error": str(error)[:500], "last_attempt_at": datetime.now(timezone.utc).isoformat()}
    await session.commit()


async def ingest_context_records(session, connection: ProviderConnection, records: list[dict[str, Any]], *, reason: str = "webhook") -> MemoryNote | None:
    if not records:
        return None
    connector = connection.provider.removeprefix("connector-")
    config = dict(connection.config or {})
    result = {
        "label": config.get("label") or connection.name,
        "records": records,
        "item_count": len(records),
        "summary": connector_preset(connector)["name"] + " webhook updates.",
        "details": config.get("details") or {},
    }
    source = connector_memory_markdown(connector, result)
    memory = await session.scalar(select(MemoryNote).where(MemoryNote.workspace_id == connection.workspace_id, MemoryNote.scope == "global"))
    if not memory:
        memory = MemoryNote(workspace_id=connection.workspace_id, scope="global", title="Main memory", summary="Long-term user context and connected knowledge sources.", content=f"# Main memory\n\n{source}")
        session.add(memory)
    else:
        memory.content = _replace_or_merge(memory.content, connector, source, True)
        memory.summary = f"Received {len(records)} new {connector} updates"
    now = datetime.now(timezone.utc).isoformat()
    connection.config = {**config, "synced_at": now, "sync_status": "ready", "last_sync_reason": reason, "last_error": None, "item_count": int(config.get("item_count") or 0) + len(records)}
    memory.byte_size = len((memory.content + memory.summary).encode("utf-8"))
    await session.flush()
    await index_memory_note(session, memory)
    await session.commit()
    return memory


async def sync_connection_by_id(connection_id: str, reason: str = "webhook") -> None:
    async with SessionFactory() as session:
        connection = await session.get(ProviderConnection, connection_id)
        if connection and connection.enabled and connection.provider.startswith("connector-"):
            try:
                await sync_context_connection(session, connection, reason=reason)
            except Exception as exc:
                await mark_sync_error(session, connection, exc)


async def periodic_context_sync() -> None:
    interval = max(60, get_settings().context_sync_interval_seconds)
    while True:
        await asyncio.sleep(interval)
        async with SessionFactory() as session:
            items = list((await session.scalars(select(ProviderConnection).where(ProviderConnection.provider.like("connector-%"), ProviderConnection.enabled.is_(True)))).all())
            for connection in items:
                try:
                    await sync_context_connection(session, connection, reason="scheduled")
                except Exception as exc:
                    logger.warning("context_sync_failed connection=%s provider=%s error=%s", connection.id, connection.provider, exc)
                    await mark_sync_error(session, connection, exc)
