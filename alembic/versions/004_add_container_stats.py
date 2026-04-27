"""Add container resource stats, image_name, and model category

Revision ID: 004_add_container_stats
Revises: 003_update_containers_extra_args
Create Date: 2026-04-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_add_container_stats"
down_revision: Union[str, None] = "003_update_containers_extra_args"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add category column to models
    op.add_column("models", sa.Column("category", sa.Text(), nullable=True))

    # Add image_name and resource stats columns to run_containers
    op.add_column("run_containers", sa.Column("image_name", sa.Text(), nullable=True))
    op.add_column("run_containers", sa.Column("max_cpu_percent", sa.Float(), nullable=True))
    op.add_column("run_containers", sa.Column("max_memory_mb", sa.Float(), nullable=True))
    op.add_column("run_containers", sa.Column("max_disk_mb", sa.Float(), nullable=True))
    op.add_column("run_containers", sa.Column("duration_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("run_containers", "duration_seconds")
    op.drop_column("run_containers", "max_disk_mb")
    op.drop_column("run_containers", "max_memory_mb")
    op.drop_column("run_containers", "max_cpu_percent")
    op.drop_column("run_containers", "image_name")
    op.drop_column("models", "category")
