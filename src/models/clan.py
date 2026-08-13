from sqlalchemy.orm import Mapped, mapped_column
try:
    from database import Base
except ModuleNotFoundError:
    from src.database import Base
from sqlalchemy import ARRAY, Integer, DateTime, func, BigInteger, String, Index
from datetime import datetime

class Clan(Base):
    __tablename__ = "ggstore_clans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id = mapped_column(BigInteger)
    platform: Mapped[str] = mapped_column(String(16), default="telegram", server_default="telegram")
    name: Mapped[str]
    game: Mapped[str]
    add_info: Mapped[str] = mapped_column(nullable=True)
    description: Mapped[str]
    demands: Mapped[str]
    photo: Mapped[str] = mapped_column(nullable=True)
    photo_origin: Mapped[str] = mapped_column(String(16), nullable=True)
    server: Mapped[str] = mapped_column(nullable=True)
    faction: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_clans_platform_user", "platform", "user_id"),
    )
