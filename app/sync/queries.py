"""
Готовые запросы для использования в боте.
"""

import datetime
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SheetEvent

async def get_events_by_date(
    session: AsyncSession,
    target_date: datetime.date,
) -> list[SheetEvent]:
    """Все мероприятия на конкретную дату."""
    query = select(SheetEvent).where(
        and_(
            SheetEvent.is_deleted == False,
            or_(
                SheetEvent.date_start == target_date,
                and_(
                    SheetEvent.date_start <= target_date,
                    SheetEvent.date_end >= target_date,
                ),
            ),
        )
    ).order_by(SheetEvent.time_start.nullslast(), SheetEvent.event_name)
    result = await session.execute(query)
    return list(result.scalars().all())

async def get_events_by_date_range(
    session: AsyncSession,
    date_from: datetime.date,
    date_to: datetime.date,
) -> list[SheetEvent]:
    """Мероприятия в диапазоне дат."""
    query = select(SheetEvent).where(
        and_(
            SheetEvent.is_deleted == False,
            SheetEvent.date_start <= date_to,
            or_(
                SheetEvent.date_end >= date_from,
                SheetEvent.date_start >= date_from,
            ),
        )
    ).order_by(SheetEvent.date_start, SheetEvent.time_start.nullslast())
    result = await session.execute(query)
    return list(result.scalars().all())

async def get_events_by_name(
    session: AsyncSession,
    name_query: str,
) -> list[SheetEvent]:
    """Поиск мероприятий по названию (частичное совпадение)."""
    query = select(SheetEvent).where(
        and_(
            SheetEvent.is_deleted == False,
            SheetEvent.event_name.ilike(f"%{name_query}%"),
        )
    ).order_by(SheetEvent.date_start.desc())
    result = await session.execute(query)
    return list(result.scalars().all())

async def get_events_by_location(
    session: AsyncSession,
    location_query: str,
) -> list[SheetEvent]:
    """Поиск мероприятий по локации."""
    query = select(SheetEvent).where(
        and_(
            SheetEvent.is_deleted == False,
            SheetEvent.location.ilike(f"%{location_query}%"),
        )
    ).order_by(SheetEvent.date_start.desc())
    result = await session.execute(query)
    return list(result.scalars().all())

async def get_events_by_color(
    session: AsyncSession,
    color_hex: str,
) -> list[SheetEvent]:
    """Мероприятия с определённым цветом ячейки."""
    query = select(SheetEvent).where(
        and_(
            SheetEvent.is_deleted == False,
            SheetEvent.cell_color_hex == color_hex.upper(),
        )
    ).order_by(SheetEvent.date_start.desc())
    result = await session.execute(query)
    return list(result.scalars().all())

async def get_today_events(session: AsyncSession) -> list[SheetEvent]:
    """Мероприятия на сегодня."""
    return await get_events_by_date(session, datetime.date.today())

async def get_week_events(session: AsyncSession) -> list[SheetEvent]:
    """Мероприятия на текущую неделю."""
    today = datetime.date.today()

    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return await get_events_by_date_range(session, monday, sunday)

async def get_unique_colors(session: AsyncSession) -> list[str]:
    """Все уникальные цвета ячеек."""
    query = (
        select(SheetEvent.cell_color_hex)
        .where(
            and_(
                SheetEvent.is_deleted == False,
                SheetEvent.cell_color_hex.isnot(None),
            )
        )
        .distinct()
    )
    result = await session.execute(query)
    return [row[0] for row in result.all()]
