"""
Парсер календарной таблицы.

Логика:
1. Ищем строки с месяцами/годами ("Ноябрь 2024", "Декабрь 2025" и т.д.)
2. Ищем строки с днями недели ("Понедельник", ..., "Воскресенье")
3. Ищем строки с числами-датами (3, 4, 5, 6, 7, 8, 9)
4. Все ячейки между строкой дат и следующей строкой дат — мероприятия
5. Определяем дату по колонке (день недели) и числу

Парсинг содержимого ячейки:
- Извлекаем время (19:00-22:00, 19-22, 15:00 - 21:00)
- Извлекаем локацию (А-200, Б-303, ПК-240, общ 1, н4, и т.д.)
- Оставшееся — название мероприятия
"""

import datetime
import logging
import re
from dataclasses import dataclass, field

from app.google_sheets.client import CellData, SheetData

logger = logging.getLogger(__name__)

MONTHS_RU = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4,
    "май": 5, "июнь": 6, "июль": 7, "август": 8,
    "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}

WEEKDAYS_RU = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}

TIME_PATTERN = re.compile(
    r'(\d{1,2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}(?::\d{2})?)'
)

LOCATION_PATTERN = re.compile(
    r'(?:'
    r'[АAаa]-?\d{3}'
    r'|[БBбb]-?\d{3}'
    r'|[НHнh]-?\d{3}'
    r'|ПК-?\d{3}[а-яa-z]?'
    r'|АВ-?\d{4}'
    r'|[ВVвv]-?\d{3}'
    r'|общ\s*\d+'
    r'|н\d+'
    r'|Добро[.\s]*[Цц]ентр'
    r'|ЦСО'
    r'|БС'
    r'|актовый\s*зал'
    r'|спортзал\s*[АA]'
    r'|ОКСТЦ\s*«?Полёт»?'
    r')',
    re.IGNORECASE,
)

@dataclass
class ParsedEvent:
    """Результат парсинга одного мероприятия."""
    event_name: str
    date_start: datetime.date | None = None
    date_end: datetime.date | None = None
    time_start: datetime.time | None = None
    time_end: datetime.time | None = None
    location: str | None = None
    cell_color_hex: str | None = None
    is_multiday: bool = False

    sheet_name: str = ""
    cell_row: int = 0
    cell_col: int = 0
    cell_address: str = ""
    raw_text: str = ""

@dataclass
class CalendarBlock:
    """Один блок календаря (месяц)."""
    year: int
    month: int

    date_row_idx: int
    col_to_day: dict[int, int] = field(default_factory=dict)

    events_row_start: int = 0
    events_row_end: int = 0

def _parse_time(text: str) -> tuple[datetime.time | None, datetime.time | None]:
    """Извлекает первое найденное время из текста."""
    m = TIME_PATTERN.search(text)
    if not m:
        return None, None

    def to_time(s: str) -> datetime.time | None:
        try:
            if ":" in s:
                parts = s.split(":")
                return datetime.time(int(parts[0]), int(parts[1]))
            else:
                h = int(s)
                if 0 <= h <= 23:
                    return datetime.time(h, 0)
        except (ValueError, IndexError):
            pass
        return None

    return to_time(m.group(1)), to_time(m.group(2))

def _extract_locations(text: str) -> str | None:
    """Извлекает все упоминания локаций из текста."""
    matches = LOCATION_PATTERN.findall(text)
    if not matches:
        return None

    seen = set()
    unique = []
    for loc in matches:
        loc_clean = loc.strip()
        if loc_clean.lower() not in seen:
            seen.add(loc_clean.lower())
            unique.append(loc_clean)
    return ", ".join(unique)

def _clean_event_name(text: str) -> str:
    """Убирает время и локации, оставляя название мероприятия."""

    cleaned = TIME_PATTERN.sub("", text)

    cleaned = LOCATION_PATTERN.sub("", cleaned)

    cleaned = re.sub(r'[\n\r]+', ' ', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = re.sub(r'[,;]\s*$', '', cleaned)
    cleaned = re.sub(r'^\s*[,;]\s*', '', cleaned)
    return cleaned.strip()

def _find_month_year(text: str) -> tuple[int, int] | None:
    """Ищет 'Месяц ГГГГ' в строке. Возвращает (month, year) или None."""
    text_lower = text.lower().strip()
    for month_name, month_num in MONTHS_RU.items():
        if month_name in text_lower:

            year_match = re.search(r'20\d{2}', text)
            if year_match:
                return month_num, int(year_match.group())
    return None

def _is_weekday_row(row_values: list[str]) -> bool:
    """Проверяет, является ли строка заголовком дней недели."""
    weekday_count = 0
    for val in row_values:
        if val.strip().lower() in WEEKDAYS_RU:
            weekday_count += 1
    return weekday_count >= 5

def _is_date_number_row(row_values: list[str]) -> bool:
    """Проверяет, является ли строка строкой с числами-датами (1-31)."""
    number_count = 0
    for val in row_values:
        val = val.strip()
        if val.isdigit() and 1 <= int(val) <= 31:
            number_count += 1
    return number_count >= 3

def _get_col_to_day(row_values: list[str]) -> dict[int, int]:
    """Из строки с числами возвращает {col_index: day_number}."""
    result = {}
    for ci, val in enumerate(row_values):
        val = val.strip()
        if val.isdigit() and 1 <= int(val) <= 31:
            result[ci] = int(val)
    return result

class CalendarParser:
    """Парсер календарной таблицы."""

    def parse(self, sheet_data: SheetData) -> list[ParsedEvent]:
        """Парсит весь лист, возвращает список мероприятий."""
        if not sheet_data.all_values:
            return []

        events: list[ParsedEvent] = []
        rows = sheet_data.all_values

        cell_map: dict[tuple[int, int], CellData] = {}
        for cell in sheet_data.cells:
            cell_map[(cell.row, cell.col)] = cell

        blocks = self._find_calendar_blocks(rows)

        if not blocks:
            logger.warning(
                f"Не удалось найти календарные блоки в '{sheet_data.sheet_name}'. "
                f"Сохраняем ячейки как есть."
            )
            return self._fallback_parse(sheet_data, cell_map)

        logger.info(
            f"Лист '{sheet_data.sheet_name}': найдено {len(blocks)} месячных блоков"
        )

        for block in blocks:
            block_events = self._parse_block(
                block, rows, cell_map, sheet_data.sheet_name
            )
            events.extend(block_events)

        logger.info(
            f"Лист '{sheet_data.sheet_name}': распарсено {len(events)} мероприятий"
        )

        events = self._detect_multiday(events)

        return events

    def _find_calendar_blocks(self, rows: list[list[str]]) -> list[CalendarBlock]:
        """Ищем все блоки: месяцдни неделичисламероприятия."""
        blocks: list[CalendarBlock] = []
        current_month: int | None = None
        current_year: int | None = None

        i = 0
        while i < len(rows):
            row = rows[i]
            full_row_text = " ".join(row)

            month_year = _find_month_year(full_row_text)
            if month_year:
                current_month, current_year = month_year
                i += 1
                continue

            if current_month and current_year and _is_date_number_row(row):
                col_to_day = _get_col_to_day(row)
                if col_to_day:

                    end = len(rows)
                    for j in range(i + 1, len(rows)):
                        next_row_text = " ".join(rows[j])
                        if _is_date_number_row(rows[j]) or _find_month_year(next_row_text):
                            end = j
                            break

                    block = CalendarBlock(
                        year=current_year,
                        month=current_month,
                        date_row_idx=i,
                        col_to_day=col_to_day,
                        events_row_start=i + 1,
                        events_row_end=end,
                    )
                    blocks.append(block)

            i += 1

        return blocks

    def _parse_block(
        self,
        block: CalendarBlock,
        rows: list[list[str]],
        cell_map: dict[tuple[int, int], CellData],
        sheet_name: str,
    ) -> list[ParsedEvent]:
        """Парсит один календарный блок (одна неделя/строка дат)."""
        events: list[ParsedEvent] = []

        for row_idx in range(block.events_row_start, block.events_row_end):
            if row_idx >= len(rows):
                break
            row = rows[row_idx]

            for col_idx, day_num in block.col_to_day.items():
                if col_idx >= len(row):
                    continue

                cell_text = row[col_idx].strip()
                if not cell_text:
                    continue

                if cell_text.lower() in WEEKDAYS_RU:
                    continue
                if cell_text.isdigit() and 1 <= int(cell_text) <= 31:
                    continue

                try:
                    event_date = datetime.date(block.year, block.month, day_num)
                except ValueError:
                    logger.warning(
                        f"Невалидная дата: {block.year}-{block.month}-{day_num}"
                    )
                    continue

                cell_data = cell_map.get((row_idx + 1, col_idx + 1))
                bg_color = cell_data.bg_color_hex if cell_data else None
                cell_addr = cell_data.address if cell_data else f"?{col_idx+1}:{row_idx+1}"

                time_start, time_end = _parse_time(cell_text)
                location = _extract_locations(cell_text)
                event_name = _clean_event_name(cell_text)

                if not event_name:
                    event_name = cell_text[:200]

                events.append(ParsedEvent(
                    event_name=event_name,
                    date_start=event_date,
                    date_end=event_date,
                    time_start=time_start,
                    time_end=time_end,
                    location=location,
                    cell_color_hex=bg_color,
                    is_multiday=False,
                    sheet_name=sheet_name,
                    cell_row=row_idx + 1,
                    cell_col=col_idx + 1,
                    cell_address=cell_addr,
                    raw_text=cell_text,
                ))

        return events

    def _detect_multiday(self, events: list[ParsedEvent]) -> list[ParsedEvent]:
        """
        Определяет многодневные мероприятия:
        если одно и то же название встречается в последовательных днях,
        объединяем в одну запись с date_start / date_end.
        """
        if not events:
            return events

        from collections import defaultdict
        groups: dict[str, list[ParsedEvent]] = defaultdict(list)

        for ev in events:
            key = f"{ev.sheet_name}||{ev.event_name.lower().strip()}"
            groups[key].append(ev)

        result: list[ParsedEvent] = []

        for key, group in groups.items():
            if len(group) <= 1:
                result.extend(group)
                continue

            group.sort(key=lambda e: e.date_start or datetime.date.min)

            chains: list[list[ParsedEvent]] = []
            current_chain: list[ParsedEvent] = [group[0]]

            for i in range(1, len(group)):
                prev_date = group[i - 1].date_start
                curr_date = group[i].date_start

                if prev_date and curr_date:
                    delta = (curr_date - prev_date).days
                    if 1 <= delta <= 2:
                        current_chain.append(group[i])
                        continue

                chains.append(current_chain)
                current_chain = [group[i]]

            chains.append(current_chain)

            for chain in chains:
                if len(chain) > 1:

                    merged = chain[0]
                    merged.date_end = chain[-1].date_start
                    merged.is_multiday = True
                    result.append(merged)

                    for ev in chain[1:]:
                        ev.is_multiday = True
                        ev.date_start = chain[0].date_start
                        ev.date_end = chain[-1].date_start
                        result.append(ev)
                else:
                    result.extend(chain)

        return result

    def _fallback_parse(
        self,
        sheet_data: SheetData,
        cell_map: dict[tuple[int, int], CellData],
    ) -> list[ParsedEvent]:
        """Фоллбэк: если структура не распознана, сохраняем всё как есть."""
        events = []
        for cell in sheet_data.cells:
            text = cell.value.strip()
            if not text:
                continue
            if text.lower() in WEEKDAYS_RU:
                continue

            time_start, time_end = _parse_time(text)
            location = _extract_locations(text)
            event_name = _clean_event_name(text)

            events.append(ParsedEvent(
                event_name=event_name or text[:200],
                date_start=None,
                date_end=None,
                time_start=time_start,
                time_end=time_end,
                location=location,
                cell_color_hex=cell.bg_color_hex,
                sheet_name=sheet_data.sheet_name,
                cell_row=cell.row,
                cell_col=cell.col,
                cell_address=cell.address,
                raw_text=text,
            ))

        return events
