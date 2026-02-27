"""Service for managing the run execution queue."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.run import Run


async def get_queue(db: AsyncSession) -> list[Run]:
    """
    Get all queued and running runs, ordered by queue_position.
    Returns both running (no queue_position) and queued runs.
    """
    result = await db.execute(
        select(Run)
        .where(Run.status.in_(["queued", "running"]))
        .order_by(Run.queue_position.asc().nullslast(), Run.created_at.asc())
    )
    return list(result.scalars().all())


async def reorder_queue(db: AsyncSession, run_ids: list[UUID]) -> None:
    """
    Reorder queued runs by assigning new queue_position values.
    Only affects runs with status 'queued'. Running runs are not reordered.
    """
    for position, run_id in enumerate(run_ids, start=1):
        await db.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "queued")
            .values(queue_position=position)
        )
    await db.flush()
