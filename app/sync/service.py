"""
Сервис синхронизации: Google Sheets PostgreSQL.

Каждые N минут:
1. Скачиваем данные из таблицы
2. Парсим мероприятия
3. Сравниваем с тем, что в БД (по sheet_name + cell_row + cell_col)
4. Создаём новые / обновляем изменённые / soft-delete удалённые
"""

import datetime
import logging
from collections import defaultdict

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.google_sheets.client import GoogleSheetsClient
from app.google_sheets.parser import CalendarParser, ParsedEvent
from app.models import SheetEvent, SyncLog
from app.config import settings

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(self):
        self.sheets_client = GoogleSheetsClient()
        self.parser = CalendarParser()

    async def sync_all_sheets(self) -> dict:
        """Синхронизирует все листы из конфигурации."""
        results = {}
        for sheet_name in settings.SHEET_NAMES:
            try:
                result = await self.sync_sheet(sheet_name)
                results[sheet_name] = result
            except Exception as e:
                logger.exception(f"Ошибка синхронизации листа '{sheet_name}': {e}")
                results[sheet_name] = {"error": str(e)}
        return results

    async def sync_sheet(self, sheet_name: str) -> dict:
        """Синхронизирует один лист."""
        logger.info(f"Начинаем синхронизацию листа: {sheet_name} ")

        stats = {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "total_parsed": 0,
            "error": None,
        }

        async with async_session_factory() as session:

            sync_log = SyncLog(sheet_name=sheet_name)
            session.add(sync_log)
            await session.flush()

            try:

                import asyncio
                loop = asyncio.get_event_loop()
                sheet_data = await loop.run_in_executor(
                    None, self.sheets_client.fetch_sheet_data, sheet_name
                )

                if not sheet_data.cells:
                    logger.info(f"Лист '{sheet_name}' пустой или не найден")
                    sync_log.finished_at = datetime.datetime.now(datetime.timezone.utc)
                    await session.commit()
                    return stats

                parsed_events = self.parser.parse(sheet_data)
                stats["total_parsed"] = len(parsed_events)
                logger.info(f"Распарсено {len(parsed_events)} мероприятий")

                existing_query = select(SheetEvent).where(
                    and_(
                        SheetEvent.sheet_name == sheet_name,
                        SheetEvent.is_deleted == False,
                    )
                )
                result = await session.execute(existing_query)
                existing_events: list[SheetEvent] = list(result.scalars().all())

                existing_map: dict[tuple[int, int], SheetEvent] = {}
                for ev in existing_events:
                    existing_map[(ev.cell_row, ev.cell_col)] = ev

                seen_keys: set[tuple[int, int]] = set()

                for parsed in parsed_events:
                    key = (parsed.cell_row, parsed.cell_col)
                    seen_keys.add(key)
                    content_hash = SheetEvent.compute_hash(parsed.raw_text)

                    if key in existing_map:
                        db_event = existing_map[key]

                        if db_event.content_hash != content_hash:

                            self._update_event(db_event, parsed, content_hash)
                            stats["updated"] += 1
                            logger.debug(
                                f"UPDATED [{parsed.cell_address}]: "
                                f"{parsed.event_name[:60]}"
                            )

                    else:

                        new_event = self._create_event(parsed, content_hash)
                        session.add(new_event)
                        stats["created"] += 1
                        logger.debug(
                            f"CREATED [{parsed.cell_address}]: "
                            f"{parsed.event_name[:60]}"
                        )

                for key, db_event in existing_map.items():
                    if key not in seen_keys:
                        db_event.is_deleted = True
                        db_event.updated_at = datetime.datetime.now(
                            datetime.timezone.utc
                        )
                        stats["deleted"] += 1
                        logger.debug(
                            f"DELETED [{db_event.cell_address}]: "
                            f"{db_event.event_name[:60]}"
                        )

                sync_log.finished_at = datetime.datetime.now(datetime.timezone.utc)
                sync_log.total_cells = len(sheet_data.cells)
                sync_log.created_count = stats["created"]
                sync_log.updated_count = stats["updated"]
                sync_log.deleted_count = stats["deleted"]

                await session.commit()

                logger.info(
                    f"Синхронизация '{sheet_name}' завершена: "
                    f"+{stats['created']} ~{stats['updated']} "
                    f"-{stats['deleted']} "
                )

            except Exception as e:
                await session.rollback()
                stats["error"] = str(e)

                sync_log.error = str(e)
                sync_log.finished_at = datetime.datetime.now(datetime.timezone.utc)

                try:
                    async with async_session_factory() as err_session:
                        err_session.add(sync_log)
                        await err_session.commit()
                except Exception:
                    pass

                logger.exception(
                    f"Ошибка при синхронизации '{sheet_name}': {e}"
                )

        return stats

    def _create_event(self, parsed: ParsedEvent, content_hash: str) -> SheetEvent:
        """Создаёт новую запись SheetEvent из распарсенных данных."""
        return SheetEvent(
            sheet_name=parsed.sheet_name,
            cell_address=parsed.cell_address,
            cell_row=parsed.cell_row,
            cell_col=parsed.cell_col,
            raw_text=parsed.raw_text,
            content_hash=content_hash,
            event_name=parsed.event_name,
            date_start=parsed.date_start,
            date_end=parsed.date_end,
            time_start=parsed.time_start,
            time_end=parsed.time_end,
            location=parsed.location,
            cell_color_hex=parsed.cell_color_hex,
            is_multiday=parsed.is_multiday,
            is_deleted=False,
        )

    def _update_event(
        self,
        db_event: SheetEvent,
        parsed: ParsedEvent,
        content_hash: str,
    ) -> None:
        """Обновляет существующую запись новыми данными."""
        db_event.raw_text = parsed.raw_text
        db_event.content_hash = content_hash
        db_event.event_name = parsed.event_name
        db_event.date_start = parsed.date_start
        db_event.date_end = parsed.date_end
        db_event.time_start = parsed.time_start
        db_event.time_end = parsed.time_end
        db_event.location = parsed.location
        db_event.cell_color_hex = parsed.cell_color_hex
        db_event.is_multiday = parsed.is_multiday
        db_event.is_deleted = False
        db_event.cell_address = parsed.cell_address
        db_event.updated_at = datetime.datetime.now(datetime.timezone.utc)
