from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db import SessionFactory
from orchestrator.models import RunEvent
from orchestrator.schemas import EventRead


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[EventRead]]] = defaultdict(set)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def publish(
        self,
        session: AsyncSession,
        *,
        run_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str | None = None,
        recipients: list[str] | None = None,
        task_id: str | None = None,
        parent_event_id: str | None = None,
        payload: dict[str, Any] | None = None,
        visibility: str = "shared",
    ) -> EventRead:
        async with self._locks[run_id]:
            event = None
            for attempt in range(5):
                last_sequence = await session.scalar(
                    select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
                )
                event = RunEvent(
                    run_id=run_id,
                    sequence=(last_sequence or 0) + 1,
                    type=event_type,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    recipients=recipients or [],
                    task_id=task_id,
                    parent_event_id=parent_event_id,
                    payload=payload or {},
                    visibility=visibility,
                )
                session.add(event)
                try:
                    await session.commit()
                    await session.refresh(event)
                    break
                except IntegrityError:
                    await session.rollback()
                    event = None
                    if attempt == 4:
                        raise
                    await asyncio.sleep(0.01 * (attempt + 1))
            assert event is not None
        value = EventRead.model_validate(event)
        for queue in tuple(self._subscribers[run_id]):
            await queue.put(value)
        return value

    async def subscribe(self, run_id: str, after_sequence: int = 0) -> AsyncIterator[str]:
        async with SessionFactory() as session:
            stored = list(
                (
                    await session.scalars(
                        select(RunEvent)
                        .where(RunEvent.run_id == run_id, RunEvent.sequence > after_sequence)
                        .order_by(RunEvent.sequence)
                    )
                ).all()
            )
        for event in stored:
            yield self._format(EventRead.model_validate(event))

        cursor = stored[-1].sequence if stored else after_sequence

        queue: asyncio.Queue[EventRead] = asyncio.Queue(maxsize=200)
        self._subscribers[run_id].add(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.75)
                    if event.sequence > cursor:
                        cursor = event.sequence
                        yield self._format(event)
                except TimeoutError:
                    # Database polling makes SSE work across multiple API processes;
                    # the in-memory queue remains the low-latency fast path.
                    async with SessionFactory() as session:
                        missed = list(
                            (
                                await session.scalars(
                                    select(RunEvent)
                                    .where(RunEvent.run_id == run_id, RunEvent.sequence > cursor)
                                    .order_by(RunEvent.sequence)
                                    .limit(200)
                                )
                            ).all()
                        )
                    if missed:
                        for stored_event in missed:
                            cursor = stored_event.sequence
                            yield self._format(EventRead.model_validate(stored_event))
                    else:
                        yield ": keep-alive\n\n"
        finally:
            self._subscribers[run_id].discard(queue)

    @staticmethod
    def _format(event: EventRead) -> str:
        data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        return f"id: {event.sequence}\nevent: {event.type}\ndata: {data}\n\n"


broker = EventBroker()
