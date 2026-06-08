"""
Интеграция в существующего Telegram-бота.

Если у вас уже есть бот и нужно добавить синхронизацию
как фоновую задачу.
"""

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import engine, Base
from app.sync.service import SyncService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_sync_service: SyncService | None = None

async def start_sync_background():
    """Вызвать при старте бота."""
    global _scheduler, _sync_service

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _sync_service = SyncService()

    asyncio.create_task(_sync_service.sync_all_sheets())

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _sync_service.sync_all_sheets,
        trigger=IntervalTrigger(minutes=settings.SYNC_INTERVAL_MINUTES),
        id="sheets_sync",
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Фоновая синхронизация Google Sheets запущена")

async def stop_sync_background():
    """Вызвать при остановке бота."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("Фоновая синхронизация остановлена")

async def force_sync(sheet_name: str | None = None) -> dict:
    """Ручной запуск синхронизации (например, по команде /sync)."""
    if not _sync_service:
        return {"error": "Сервис не инициализирован"}

    if sheet_name:
        return await _sync_service.sync_sheet(sheet_name)
    return await _sync_service.sync_all_sheets()
