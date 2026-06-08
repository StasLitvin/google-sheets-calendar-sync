
from aiogram import Bot, Dispatcher, Router
from app.sync.integration import start_sync_background, stop_sync_background

bot = Bot(token="...")
dp = Dispatcher()

@dp.startup()
async def on_startup():
    await start_sync_background()

@dp.shutdown()
async def on_shutdown():
    await stop_sync_background()

from aiogram.types import Message
from app.database import async_session_factory
from app.sync.queries import get_today_events

router = Router()

@router.message(lambda m: m.text == "/today")
async def cmd_today(message: Message):
    async with async_session_factory() as session:
        events = await get_today_events(session)

    if not events:
        await message.answer("На сегодня мероприятий нет")
        return

    lines = []
    for ev in events:
        time_str = ""
        if ev.time_start and ev.time_end:
            time_str = f" {ev.time_start:%H:%M}-{ev.time_end:%H:%M}"
        loc_str = f" {ev.location}" if ev.location else ""
        color_dot = f"" if ev.cell_color_hex else ""
        lines.append(f"{color_dot} <b>{ev.event_name}</b>{time_str}{loc_str}")

    await message.answer(
        f"Мероприятия на сегодня ({len(events)}):\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )
