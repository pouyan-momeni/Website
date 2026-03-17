"""Migrate docker_images env dict to extra_args string

Revision ID: 003_update_containers_extra_args
Revises: 002_add_audit_logs
Create Date: 2026-03-16 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "003_update_containers_extra_args"
down_revision: Union[str, None] = "002_add_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert env dict to extra_args string in existing docker_images JSONB
    op.execute("""
        UPDATE models
        SET docker_images = (
            SELECT COALESCE(jsonb_agg(
                CASE
                    WHEN item ? 'env' THEN
                        jsonb_set(
                            item - 'env',
                            '{extra_args}',
                            to_jsonb(
                                COALESCE(
                                    array_to_string(
                                        array(SELECT '-e ' || key || '=' || value FROM jsonb_each_text(item->'env')),
                                        E'\\n'
                                    ),
                                    ''
                                )
                            )
                        )
                    ELSE item || '{"extra_args": ""}'::jsonb
                END
            ), '[]'::jsonb)
            FROM jsonb_array_elements(docker_images) AS item
        )
        WHERE docker_images IS NOT NULL AND jsonb_array_length(docker_images) > 0;
    """)


def downgrade() -> None:
    # Convert extra_args string back to env dict
    op.execute("""
        UPDATE models
        SET docker_images = (
            SELECT COALESCE(jsonb_agg(
                CASE
                    WHEN item ? 'extra_args' THEN
                        jsonb_set(
                            item - 'extra_args',
                            '{env}',
                            '{}'::jsonb
                        )
                    ELSE item || '{"env": {}}'::jsonb
                END
            ), '[]'::jsonb)
            FROM jsonb_array_elements(docker_images) AS item
        )
        WHERE docker_images IS NOT NULL AND jsonb_array_length(docker_images) > 0;
    """)
