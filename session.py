# app/db/session.py (фрагмент)
import aiosqlite
from app.config import settings

DB_PATH = settings.db_path  # <-- путь из config.py

def get_conn():
    return aiosqlite.connect(DB_PATH.as_posix())

async def init_db():
    from pathlib import Path
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        with open(schema_path, "r", encoding="utf-8") as f:
            await db.executescript(f.read())
        await db.commit()
