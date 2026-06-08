"""
Клиент для работы с Google Sheets API.

Используем два уровня:
1. gspread — удобно читать текст ячеек
2. google-api-python-client — получаем форматирование (цвета ячеек)
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

@dataclass
class CellData:
    """Данные одной ячейки."""
    row: int
    col: int
    address: str
    value: str
    bg_color_hex: str | None = None

@dataclass
class SheetData:
    """Все данные одного листа."""
    sheet_name: str
    cells: list[CellData] = field(default_factory=list)
    all_values: list[list[str]] = field(default_factory=list)
    row_count: int = 0
    col_count: int = 0

class GoogleSheetsClient:
    """Обёртка для работы с таблицей."""

    def __init__(self):
        self._credentials = Credentials.from_service_account_file(
            settings.GOOGLE_CREDENTIALS_FILE,
            scopes=SCOPES,
        )
        self._gc = gspread.authorize(self._credentials)
        self._service = build(
            "sheets", "v4", credentials=self._credentials, cache_discovery=False
        )
        self._spreadsheet_id = settings.SPREADSHEET_ID

    def _col_letter(self, col: int) -> str:
        """1 -> A, 2 -> B, ... 27 -> AA ..."""
        result = ""
        while col > 0:
            col, remainder = divmod(col - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def fetch_sheet_data(self, sheet_name: str) -> SheetData:
        """
        Загружает ВСЕ данные листа: текст + цвета фона.
        Возвращает SheetData с заполненным списком CellData.
        """
        logger.info(f"Загрузка листа: {sheet_name}")

        try:
            spreadsheet = self._gc.open_by_key(self._spreadsheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            logger.warning(f"Лист '{sheet_name}' не найден, пропускаем")
            return SheetData(sheet_name=sheet_name)

        all_values: list[list[str]] = worksheet.get_all_values()
        if not all_values:
            return SheetData(sheet_name=sheet_name)

        row_count = len(all_values)
        col_count = max(len(row) for row in all_values) if all_values else 0

        range_notation = (
            f"'{sheet_name}'!A1:{self._col_letter(col_count)}{row_count}"
        )

        resp = (
            self._service.spreadsheets()
            .get(
                spreadsheetId=self._spreadsheet_id,
                ranges=[range_notation],
                fields="sheets.data.rowData.values.effectiveFormat.backgroundColor",
                includeGridData=True,
            )
            .execute()
        )

        color_map: dict[tuple[int, int], dict] = {}
        sheets_data = resp.get("sheets", [])
        if sheets_data:
            grid_data = sheets_data[0].get("data", [])
            if grid_data:
                for ri, row_data in enumerate(grid_data[0].get("rowData", [])):
                    for ci, cell_val in enumerate(row_data.get("values", [])):
                        eff = cell_val.get("effectiveFormat", {})
                        bg = eff.get("backgroundColor")
                        if bg:
                            color_map[(ri, ci)] = bg

        from app.google_sheets.color_utils import gsheets_color_to_hex

        cells: list[CellData] = []

        for ri, row in enumerate(all_values):
            for ci, value in enumerate(row):
                text = (value or "").strip()
                if not text:
                    continue

                bg_raw = color_map.get((ri, ci))
                bg_hex = gsheets_color_to_hex(bg_raw)

                address = f"{self._col_letter(ci + 1)}{ri + 1}"

                cells.append(CellData(
                    row=ri + 1,
                    col=ci + 1,
                    address=address,
                    value=text,
                    bg_color_hex=bg_hex,
                ))

        sheet_data = SheetData(
            sheet_name=sheet_name,
            cells=cells,
            all_values=all_values,
            row_count=row_count,
            col_count=col_count,
        )

        logger.info(
            f"Лист '{sheet_name}': {row_count} строк, "
            f"{col_count} столбцов, {len(cells)} непустых ячеек"
        )

        return sheet_data
