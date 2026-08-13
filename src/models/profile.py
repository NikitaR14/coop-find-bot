from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from database import Base
except ModuleNotFoundError:
    from src.database import Base
from sqlalchemy import Integer, Date, ForeignKey, BigInteger, String, Index
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import date


class Profile(Base):
    __tablename__ = "ggstore_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    platform: Mapped[str] = mapped_column(
        String(16), default="telegram", server_default="telegram"
    )
    nickname: Mapped[str] = mapped_column(String(32))
    age: Mapped[int] = mapped_column(Integer, nullable=True)
    telegram_tag: Mapped[str] = mapped_column(nullable=True)
    gender: Mapped[str] = mapped_column(nullable=True)
    games: Mapped[list["Game"]] = relationship("Game", back_populates="profile")
    about: Mapped[str]
    goal: Mapped[str] = mapped_column(nullable=True)
    goals = mapped_column(ARRAY(String), default=[])
    convenient_time = mapped_column(ARRAY(String), default=[])
    photo: Mapped[str] = mapped_column(nullable=True)
    photo_origin: Mapped[str] = mapped_column(String(16), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=False)
    self_deactivated: Mapped[bool] = mapped_column(default=False, nullable=True)

    teammate_ids = mapped_column(ARRAY(Integer), default=[])
    polite: Mapped[float] = mapped_column(nullable=True)
    skill: Mapped[float] = mapped_column(nullable=True)
    team_game: Mapped[float] = mapped_column(nullable=True)
    legacy_polite: Mapped[float] = mapped_column(nullable=True)
    legacy_skill: Mapped[float] = mapped_column(nullable=True)
    legacy_team_game: Mapped[float] = mapped_column(nullable=True)
    legacy_review_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    experience: Mapped[int] = mapped_column(default=0)
    send_first_message: Mapped[bool] = mapped_column(default=False)
    last_activity_day: Mapped[date]
    days_series: Mapped[int] = mapped_column(default=1)

    @property
    def games_str(self) -> str:
        return ", ".join([game.name for game in self.games])

    __table_args__ = (Index("ix_profiles_platform_user", "platform", "user_id"),)


class Game(Base):
    __tablename__ = "ggstore_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    rank: Mapped[str] = mapped_column(nullable=True)
    server: Mapped[str] = mapped_column(nullable=True)
    faction: Mapped[str] = mapped_column(nullable=True)
    gallery: Mapped[list[str]] = mapped_column(ARRAY(String), default=[], nullable=True)

    profile_id: Mapped[int] = mapped_column(ForeignKey("ggstore_profiles.id"))
    profile: Mapped["Profile"] = relationship("Profile", back_populates="games")
