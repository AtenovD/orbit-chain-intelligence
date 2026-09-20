from datetime import datetime, timedelta, timezone

from orchestrator.db import SessionFactory
from orchestrator.models import InteractionMode, Run, RunStatus, Team, Workspace
from orchestrator.runtime import RuntimeManager


async def test_expired_worker_lease_can_be_reclaimed_without_restart():
    workspace = Workspace(name="Recovery")
    async with SessionFactory() as session:
        session.add(workspace)
        await session.flush()
        team = Team(workspace_id=workspace.id, name="Crew", goal="Recover work")
        session.add(team)
        await session.flush()
        run = Run(
            team_id=team.id,
            goal="Resume from checkpoint",
            mode=InteractionMode.standard,
            status=RunStatus.running,
            worker_id="dead-worker",
            lease_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    manager = RuntimeManager()
    async with SessionFactory() as session:
        assert await manager._acquire_lease(session, run_id) is True
        refreshed = await session.get(Run, run_id)
        assert refreshed.worker_id == manager.worker_id
        assert refreshed.lease_until is not None
        lease_until = refreshed.lease_until
        if lease_until.tzinfo is None:
            lease_until = lease_until.replace(tzinfo=timezone.utc)
        assert lease_until > datetime.now(timezone.utc)


async def test_recover_enqueues_only_resumable_run_statuses(monkeypatch):
    workspace = Workspace(name="Recovery queue")
    async with SessionFactory() as session:
        session.add(workspace)
        await session.flush()
        team = Team(workspace_id=workspace.id, name="Crew", goal="Recover work")
        session.add(team)
        await session.flush()
        active = Run(team_id=team.id, goal="Running", mode=InteractionMode.standard, status=RunStatus.running)
        waiting = Run(team_id=team.id, goal="Waiting", mode=InteractionMode.standard, status=RunStatus.waiting_for_human)
        done = Run(team_id=team.id, goal="Done", mode=InteractionMode.standard, status=RunStatus.completed)
        session.add_all([active, waiting, done])
        await session.commit()
        expected = {active.id, waiting.id}

    manager = RuntimeManager()
    resumed: list[tuple[str, bool]] = []

    async def capture(run_id: str, *, recovered: bool = False):
        resumed.append((run_id, recovered))

    monkeypatch.setattr(manager, "start", capture)
    await manager.recover()
    assert {run_id for run_id, _ in resumed} == expected
    assert all(recovered for _, recovered in resumed)
