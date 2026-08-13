"""restore the production-only schema revision

Revision ID: 4350fedbbac0
Revises: 5360c4b7989d
Create Date: 2026-08-13 08:20:00

The production database was stamped with this revision, but its migration file
was not committed to the original repository.  The statements below describe
the production-only columns observed before the Discord rollout and remain
idempotent for older development databases.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "4350fedbbac0"
down_revision: Union[str, Sequence[str], None] = "5360c4b7989d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ggstore_profiles "
        "ADD COLUMN IF NOT EXISTS convenient_time VARCHAR[]"
    )
    op.execute(
        "ALTER TABLE ggstore_profiles "
        "ADD COLUMN IF NOT EXISTS self_deactivated BOOLEAN"
    )
    op.execute(
        "ALTER TABLE ggstore_clans ADD COLUMN IF NOT EXISTS add_info VARCHAR"
    )
    op.execute(
        "ALTER TABLE ggstore_profiles ALTER COLUMN user_id TYPE BIGINT"
    )
    op.execute("ALTER TABLE ggstore_clans ALTER COLUMN user_id TYPE BIGINT")
    op.execute("ALTER TABLE ggstore_clans ALTER COLUMN user_id DROP NOT NULL")


def downgrade() -> None:
    # This revision reconstructs production history.  Dropping these columns
    # would destroy live profile and clan data, so downgrade is intentionally
    # non-destructive.
    pass
