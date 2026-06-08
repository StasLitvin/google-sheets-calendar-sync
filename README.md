# calendar — синхронизация с Google Sheets

Сервис двусторонней синхронизации мероприятий между Google Sheets и базой данных, с aiogram-ботом и миграциями Alembic. Может работать как отдельный сервис или как фоновая задача внутри бота.

## Структура

```
calendar/
├── main.py                  # точка входа: периодическая синхронизация (APScheduler)
├── bot.py                   # интеграция фоновой синхронизации в aiogram-бот
├── requirements.txt
├── alembic.ini, alembic/    # миграции БД
└── app/
    ├── config.py, database.py, models.py
    ├── google_sheets/       # client.py, parser.py, color_utils.py
    └── sync/                # service.py, integration.py, queries.py
```

## Технологии

aiogram 3, SQLAlchemy, Alembic, APScheduler, Google Sheets API (gspread / google-api-python-client).

## Запуск

```bash
pip install -r requirements.txt
alembic upgrade head
# задайте параметры БД, токен бота и учётные данные Google в .env
python -m app.main      # либо: python main.py
```

## Замечания

- Для доступа к Google Sheets нужен сервисный аккаунт (JSON-ключ) — храните его вне репозитория.
