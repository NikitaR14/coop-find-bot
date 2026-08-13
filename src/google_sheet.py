from gspread import service_account
from gspread.exceptions import WorksheetNotFound
from pathlib import Path
from logging import getLogger

logger = getLogger('GoogleSheetService')


class GoogleSheetService:
    def __init__(self, credentials_path: Path, sheet_id: str, worksheet: str):
        """Инициализая объекта для работы с Google Sheet"""
        self.google_service = service_account(filename=credentials_path)
        self.sheet = self.google_service.open_by_key(key=sheet_id)
        try:
            self.worksheet = self.sheet.worksheet(title=worksheet)
        except WorksheetNotFound:
            self.worksheet = self.sheet.add_worksheet(title=worksheet, rows=100, cols=10)

    def insert_row(self, row: list) -> int:
        """Вставка строки в конец таблицы. Возвращает индекс вставленной строки."""
        self.worksheet.append_row(row)
        return len(self.worksheet.get_all_values())

    def get_row_index(self, value: str, column: int = 1) -> int | None:
        """Поиск строки по значению в указанном столбце. Возвращает индекс строки (1-based) или None"""
        all_values = self.worksheet.get_all_values()
        for i, row in enumerate(all_values):
            if len(row) >= column and row[column - 1] == value:
                return i + 1
        return None

    def get_row_index_multi(self, criteria: dict) -> int | None:
        """Поиск строки по нескольким колонкам. criteria = {col_index: value}"""
        all_values = self.worksheet.get_all_values()
        for i, row in enumerate(all_values):
            if all(
                len(row) > col and str(row[col]) == str(val)
                for col, val in criteria.items()
            ):
                return i + 1
        return None

    def update_row(self, index: int, data: dict):
        """
        Обновляет только указанные ячейки в строке.
        data = {номер_колонки: новое_значение}
        """
        logger.debug("index = %d, data = %s", index, data)
        for col_index, value in data.items():
            self.worksheet.update_cell(index, col_index + 1, value)

    def get_cell_value(self, row: int, col: int) -> str | None:
        """Получить значение ячейки по индексу строки и колонки (1-based)"""
        try:
            return self.worksheet.cell(row, col).value
        except Exception as e:
            logger.error("Error getting cell value: %s", e)
            return None
