"""
Модели БД.

Ключевые моменты:
- event может длиться несколько дней (date_start / date_end)
- время и локация необязательны (могут дополнить позже)
- cell_color хранит hex-цвет фона ячейки
- cell_address хранит адрес ячейки (e.g. "B5") для точной привязки
- content_hash нужен чтобы понять изменилось ли содержимое ячейки
"""

import datetime
import hashlib
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class SheetEvent(Base):
    """Одна запись = одно мероприятие из одной ячейки (или группы ячеек)."""

    __tablename__ = "sheet_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Имя листа")
    cell_address: Mapped[str] = mapped_column(String(16), nullable=False, comment="Адрес ячейки, напр. C12")
    cell_row: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_col: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="Исходный текст ячейки как есть")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="SHA-256 от raw_text для быстрого сравнения")

    event_name: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="Название мероприятия")
    date_start: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True, comment="Дата начала")
    date_end: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True, comment="Дата окончания (если многодневное)")
    time_start: Mapped[Optional[datetime.time]] = mapped_column(Time, nullable=True, comment="Время начала")
    time_end: Mapped[Optional[datetime.time]] = mapped_column(Time, nullable=True, comment="Время окончания")
    location: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="Аудитория / локация")

    cell_color_hex: Mapped[Optional[str]] = mapped_column(
        String(7),
        nullable=True,
        comment="Цвет фона ячейки #RRGGBB"
    )

    is_multiday: Mapped[bool] = mapped_column(Boolean, default=False, comment="Многодневное мероприятие")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="Soft-delete: мероприятие удалено из таблицы")

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_sheet_event_lookup", "sheet_name", "cell_row", "cell_col"),
        Index("ix_sheet_event_date", "date_start", "date_end"),
        Index("ix_sheet_event_hash", "sheet_name", "content_hash"),
        Index("ix_sheet_event_name", "event_name"),
    )

    @staticmethod
    def compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return (
            f"<SheetEvent id={self.id} name={self.event_name!r} "
            f"date={self.date_start} cell={self.cell_address}>"
        )

class SyncLog(Base):
    """Лог каждой синхронизации."""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)
    total_cells: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
