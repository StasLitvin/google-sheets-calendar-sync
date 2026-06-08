import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:PASSWORD@localhost:5432/KPI_bot_SO"
    )

    DATABASE_URL_SYNC: str = DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )

    GOOGLE_CREDENTIALS_FILE: str = os.getenv(
        "GOOGLE_CREDENTIALS_FILE", "credentials.json"
    )
    SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "")

    SYNC_INTERVAL_MINUTES: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "10"))

    SHEET_NAMES: list[str] = [
        "Календарь 2024",
        "Календарь 2025",
        "Календарь 2026",
        "Мероприятия",
    ]

settings = Settings()
