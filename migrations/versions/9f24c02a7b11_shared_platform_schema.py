"""shared platform schema

Revision ID: 9f24c02a7b11
Revises: 4350fedbbac0
Create Date: 2026-08-12 13:15:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "9f24c02a7b11"
down_revision: Union[str, Sequence[str], None] = "4350fedbbac0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw PostgreSQL is intentional: production contains a few columns added
    # outside the committed Alembic history, so every additive change is
    # idempotent and safe for the existing 3k profiles.
    op.execute(
        "ALTER TABLE ggstore_profiles ADD COLUMN IF NOT EXISTS platform VARCHAR(16)"
    )
    op.execute(
        "UPDATE ggstore_profiles SET platform = 'telegram' WHERE platform IS NULL"
    )
    op.execute(
        "ALTER TABLE ggstore_profiles ALTER COLUMN platform SET DEFAULT 'telegram'"
    )
    op.execute("ALTER TABLE ggstore_profiles ALTER COLUMN platform SET NOT NULL")
    op.execute("ALTER TABLE ggstore_profiles ADD COLUMN IF NOT EXISTS age INTEGER")
    op.execute(
        "ALTER TABLE ggstore_profiles ADD COLUMN IF NOT EXISTS photo_origin VARCHAR(16)"
    )
    op.execute(
        "UPDATE ggstore_profiles SET photo_origin = 'telegram' WHERE photo IS NOT NULL AND photo_origin IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_profiles_platform_user "
        "ON ggstore_profiles (platform, user_id)"
    )
    op.execute(
        "ALTER TABLE ggstore_profiles ADD COLUMN IF NOT EXISTS legacy_polite DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE ggstore_profiles ADD COLUMN IF NOT EXISTS legacy_skill DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE ggstore_profiles ADD COLUMN IF NOT EXISTS legacy_team_game DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE ggstore_profiles ADD COLUMN IF NOT EXISTS legacy_review_count INTEGER DEFAULT 0"
    )
    op.execute("ALTER TABLE ggstore_games ADD COLUMN IF NOT EXISTS server VARCHAR")
    op.execute("ALTER TABLE ggstore_games ADD COLUMN IF NOT EXISTS faction VARCHAR")
    op.execute(
        """
        UPDATE ggstore_profiles
        SET legacy_polite = polite,
            legacy_skill = skill,
            legacy_team_game = team_game,
            legacy_review_count = CASE
                WHEN polite IS NOT NULL OR skill IS NOT NULL OR team_game IS NOT NULL
                THEN GREATEST(COALESCE(cardinality(teammate_ids), 0), 1)
                ELSE 0
            END
        WHERE legacy_review_count = 0
          AND (polite IS NOT NULL OR skill IS NOT NULL OR team_game IS NOT NULL)
        """
    )

    op.execute(
        "ALTER TABLE ggstore_clans ADD COLUMN IF NOT EXISTS platform VARCHAR(16)"
    )
    op.execute("UPDATE ggstore_clans SET platform = 'telegram' WHERE platform IS NULL")
    op.execute("ALTER TABLE ggstore_clans ALTER COLUMN platform SET DEFAULT 'telegram'")
    op.execute("ALTER TABLE ggstore_clans ALTER COLUMN platform SET NOT NULL")
    op.execute(
        "ALTER TABLE ggstore_clans ADD COLUMN IF NOT EXISTS photo_origin VARCHAR(16)"
    )
    op.execute(
        "UPDATE ggstore_clans SET photo_origin = 'telegram' WHERE photo IS NOT NULL AND photo_origin IS NULL"
    )
    op.execute("ALTER TABLE ggstore_clans ADD COLUMN IF NOT EXISTS server VARCHAR")
    op.execute("ALTER TABLE ggstore_clans ADD COLUMN IF NOT EXISTS faction VARCHAR")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clans_platform_user "
        "ON ggstore_clans (platform, user_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_requests (
            id BIGSERIAL PRIMARY KEY,
            sender_profile_id BIGINT NOT NULL REFERENCES ggstore_profiles(id) ON DELETE CASCADE,
            target_profile_id BIGINT NOT NULL REFERENCES ggstore_profiles(id) ON DELETE CASCADE,
            kind VARCHAR(24) NOT NULL,
            game VARCHAR,
            message TEXT,
            status VARCHAR(24) NOT NULL DEFAULT 'sent',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            reminder_due_at TIMESTAMPTZ,
            reminder_sent_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contact_requests_sender_profile_id ON contact_requests (sender_profile_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contact_requests_target_profile_id ON contact_requests (target_profile_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contact_requests_due ON contact_requests (reminder_due_at, reminder_sent_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS profile_reviews (
            id BIGSERIAL PRIMARY KEY,
            reviewer_profile_id BIGINT NOT NULL REFERENCES ggstore_profiles(id) ON DELETE CASCADE,
            target_profile_id BIGINT NOT NULL REFERENCES ggstore_profiles(id) ON DELETE CASCADE,
            contact_request_id BIGINT REFERENCES contact_requests(id) ON DELETE SET NULL,
            polite INTEGER NOT NULL CHECK (polite BETWEEN 1 AND 5),
            skill INTEGER NOT NULL CHECK (skill BETWEEN 1 AND 5),
            team_game INTEGER NOT NULL CHECK (team_game BETWEEN 1 AND 5),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_profile_review_pair UNIQUE (reviewer_profile_id, target_profile_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_profile_reviews_reviewer_profile_id ON profile_reviews (reviewer_profile_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_profile_reviews_target_profile_id ON profile_reviews (target_profile_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experience_events (
            id BIGSERIAL PRIMARY KEY,
            profile_id BIGINT NOT NULL REFERENCES ggstore_profiles(id) ON DELETE CASCADE,
            event_type VARCHAR(32) NOT NULL,
            amount INTEGER NOT NULL,
            reference_type VARCHAR(32),
            reference_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_experience_event_reference
                UNIQUE (profile_id, event_type, reference_type, reference_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experience_events_profile_id ON experience_events (profile_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experience_events_profile_type_created "
        "ON experience_events (profile_id, event_type, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS experience_events")
    op.execute("DROP TABLE IF EXISTS profile_reviews")
    op.execute("DROP TABLE IF EXISTS contact_requests")
    op.execute("DROP INDEX IF EXISTS ix_clans_platform_user")
    op.execute("ALTER TABLE ggstore_clans DROP COLUMN IF EXISTS faction")
    op.execute("ALTER TABLE ggstore_clans DROP COLUMN IF EXISTS server")
    op.execute("ALTER TABLE ggstore_clans DROP COLUMN IF EXISTS photo_origin")
    op.execute("ALTER TABLE ggstore_clans DROP COLUMN IF EXISTS platform")
    op.execute("DROP INDEX IF EXISTS ix_profiles_platform_user")
    op.execute("ALTER TABLE ggstore_profiles DROP COLUMN IF EXISTS legacy_review_count")
    op.execute("ALTER TABLE ggstore_profiles DROP COLUMN IF EXISTS legacy_team_game")
    op.execute("ALTER TABLE ggstore_profiles DROP COLUMN IF EXISTS legacy_skill")
    op.execute("ALTER TABLE ggstore_profiles DROP COLUMN IF EXISTS legacy_polite")
    op.execute("ALTER TABLE ggstore_profiles DROP COLUMN IF EXISTS photo_origin")
    op.execute("ALTER TABLE ggstore_profiles DROP COLUMN IF EXISTS age")
    op.execute("ALTER TABLE ggstore_profiles DROP COLUMN IF EXISTS platform")
    op.execute("ALTER TABLE ggstore_games DROP COLUMN IF EXISTS faction")
    op.execute("ALTER TABLE ggstore_games DROP COLUMN IF EXISTS server")
