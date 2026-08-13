from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

try:
    from database import Base
except ModuleNotFoundError:
    from src.database import Base


class ContactRequest(Base):
    """Durable message/invitation shared by Telegram and Discord workers."""

    __tablename__ = "contact_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sender_profile_id: Mapped[int] = mapped_column(
        ForeignKey("ggstore_profiles.id", ondelete="CASCADE"), index=True
    )
    target_profile_id: Mapped[int] = mapped_column(
        ForeignKey("ggstore_profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24))
    game: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), default="sent", server_default="sent"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reminder_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_contact_requests_due", "reminder_due_at", "reminder_sent_at"),
    )


class Review(Base):
    """Latest editable rating from one profile to another."""

    __tablename__ = "profile_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reviewer_profile_id: Mapped[int] = mapped_column(
        ForeignKey("ggstore_profiles.id", ondelete="CASCADE"), index=True
    )
    target_profile_id: Mapped[int] = mapped_column(
        ForeignKey("ggstore_profiles.id", ondelete="CASCADE"), index=True
    )
    contact_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("contact_requests.id", ondelete="SET NULL"), nullable=True
    )
    polite: Mapped[int] = mapped_column(Integer)
    skill: Mapped[int] = mapped_column(Integer)
    team_game: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "reviewer_profile_id",
            "target_profile_id",
            name="uq_profile_review_pair",
        ),
    )


class ExperienceEvent(Base):
    """Auditable XP event used for daily caps and idempotent rewards."""

    __tablename__ = "experience_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("ggstore_profiles.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_experience_events_profile_type_created",
            "profile_id",
            "event_type",
            "created_at",
        ),
        UniqueConstraint(
            "profile_id",
            "event_type",
            "reference_type",
            "reference_id",
            name="uq_experience_event_reference",
        ),
    )
