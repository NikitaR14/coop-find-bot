from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
try:
    from config import settings
except ModuleNotFoundError:  # Alembic imports the package as ``src.database``.
    from src.config import settings


engine = create_async_engine(
    url=settings.db_url,
    future=True,
    echo=False, 
    pool_pre_ping=True
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    autoflush=False,
    expire_on_commit=False,
)



class Base(DeclarativeBase):
    pass
