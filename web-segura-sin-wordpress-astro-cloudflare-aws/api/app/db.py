from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import ajustes


class Base(DeclarativeBase):
    pass


class Contacto(Base):
    """La tabla la crea sql/esquema.sql con un usuario administrador; la API no tiene permisos para crear tablas."""

    __tablename__ = "contactos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    nombre: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    mensaje: Mapped[str] = mapped_column(Text)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)


motor = create_engine(ajustes.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
Sesion = sessionmaker(motor, expire_on_commit=False)
