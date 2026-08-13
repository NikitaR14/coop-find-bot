from sqlalchemy.orm import Mapped, mapped_column
try:
    from database import Base
except ModuleNotFoundError:
    from src.database import Base
from sqlalchemy import BigInteger, DateTime, func, String
from datetime import datetime


class User(Base):
    __tablename__ = "user"

    row_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String, nullable=True)
    last_name: Mapped[str] = mapped_column(String, nullable=True)
    utm_label: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    clicks: Mapped[int] = mapped_column(default=0, nullable=True)
    last_pop_up: Mapped[int] = mapped_column(default=-1, nullable=True)
