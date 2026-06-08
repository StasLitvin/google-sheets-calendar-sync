"""
Точка входа: запускает периодическую синхронизацию.

Может работать:
1. Как standalone сервис (python -m app.main)
2. Как фоновая задача внутри бота
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import engine, Base
from app.sync.service import SyncService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sync.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

logging.getLogger("googleapiclient").setLevel(logging.WARNING)
logging.getLogger("google.auth").setLevel(logging.WARNING)

sync_service = SyncService()
scheduler = AsyncIOScheduler()

async def init_db():
    """Создаёт таблицы если их нет."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("БД инициализирована")

async def run_sync():
    """Одна итерация синхронизации."""
    logger.info(f"{'='*60}")
    logger.info(f"Запуск синхронизации: {datetime.now()}")
    logger.info(f"{'='*60}")

    try:
        results = await sync_service.sync_all_sheets()
        for sheet, stats in results.items():
            if isinstance(stats, dict) and stats.get("error"):
                logger.error(f"  {sheet}: ОШИБКА — {stats['error']}")
            else:
                logger.info(f"  {sheet}: {stats}")
    except Exception as e:
        logger.exception(f"Критическая ошибка синхронизации: {e}")

async def main():
    """Главная функция."""
    logger.info("Запуск сервиса синхронизации Google Sheets PostgreSQL")
    logger.info(f"Spreadsheet ID: {settings.SPREADSHEET_ID}")
    logger.info(f"Интервал синхронизации: {settings.SYNC_INTERVAL_MINUTES} мин")
    logger.info(f"Листы: {settings.SHEET_NAMES}")

    await init_db()

    await run_sync()

    scheduler.add_job(
        run_sync,
        trigger=IntervalTrigger(minutes=settings.SYNC_INTERVAL_MINUTES),
        id="google_sheets_sync",
        name="Синхронизация Google Sheets",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()

    logger.info(
        f"Планировщик запущен. "
        f"Следующая синхронизация через {settings.SYNC_INTERVAL_MINUTES} мин."
    )

    stop_event = asyncio.Event()

    def shutdown(sig, frame):
        logger.info(f"Получен сигнал {sig}, завершаем...")
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    await stop_event.wait()

    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("Сервис остановлен")

if __name__ == "__main__":
    asyncio.run(main())
