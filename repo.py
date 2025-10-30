from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

import aiosqlite

@dataclass
class User:
    user_id: int
    tz: str
    default_remind_min: int

@dataclass
class Task:
    id: int
    user_id: int
    title: str
    start_utc: datetime
    duration_min: int
    remind_before_min: int
    tz: str
    icloud_event_href: Optional[str] = None

class UserRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def ensure_user(self, user_id: int):
        await self.db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
        await self.db.commit()

    async def get(self, user_id: int) -> Optional[User]:
        cur = await self.db.execute("SELECT user_id, tz, default_remind_min FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        return User(*row)

    async def set_tz(self, user_id: int, tz: str):
        await self.db.execute("UPDATE users SET tz=? WHERE user_id=?", (tz, user_id))
        await self.db.commit()

    async def set_default_remind(self, user_id: int, minutes: int):
        await self.db.execute("UPDATE users SET default_remind_min=? WHERE user_id=?", (minutes, user_id))
        await self.db.commit()

class TaskRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add(self, user_id: int, title: str, start_utc: datetime, duration_min: int, remind_before_min: int, tz: str) -> int:
        cur = await self.db.execute(
            "INSERT INTO tasks (user_id, title, start_utc, duration_min, remind_before_min, tz) VALUES (?,?,?,?,?,?)",
            (user_id, title, start_utc.isoformat(), duration_min, remind_before_min, tz)
        )
        await self.db.commit()
        return cur.lastrowid

    async def update_title(self, task_id: int, user_id: int, title: str):
        await self.db.execute("UPDATE tasks SET title=? WHERE id=? AND user_id=?", (title, task_id, user_id))
        await self.db.commit()

    async def update_start(self, task_id: int, user_id: int, start_utc: datetime):
        await self.db.execute("UPDATE tasks SET start_utc=? WHERE id=? AND user_id=?", (start_utc.isoformat(), task_id, user_id))
        await self.db.commit()

    async def update_duration(self, task_id: int, user_id: int, duration_min: int):
        await self.db.execute("UPDATE tasks SET duration_min=? WHERE id=? AND user_id=?", (duration_min, task_id, user_id))
        await self.db.commit()

    async def update_reminder(self, task_id: int, user_id: int, minutes: int):
        await self.db.execute("UPDATE tasks SET remind_before_min=? WHERE id=? AND user_id=?", (minutes, task_id, user_id))
        await self.db.commit()

    async def set_icloud_href(self, task_id: int, href: str):
        await self.db.execute("UPDATE tasks SET icloud_event_href=? WHERE id=?", (href, task_id))
        await self.db.commit()

    async def delete(self, task_id: int, user_id: int):
        await self.db.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, user_id))
        await self.db.commit()

    async def list_upcoming(self, user_id: int, limit: int = 20) -> Sequence[tuple]:
        cur = await self.db.execute(
            "SELECT id, title, start_utc, duration_min, remind_before_min, tz, icloud_event_href FROM tasks WHERE user_id=? ORDER BY start_utc ASC LIMIT ?",
            (user_id, limit)
        )
        return await cur.fetchall()

    async def get_core(self, task_id: int, user_id: int):
        cur = await self.db.execute("SELECT title, remind_before_min, tz, duration_min FROM tasks WHERE id=? AND user_id=?", (task_id, user_id))
        return await cur.fetchone()

    async def get_start_title_tz(self, task_id: int, user_id: int):
        cur = await self.db.execute("SELECT start_utc, title, tz FROM tasks WHERE id=? AND user_id=?", (task_id, user_id))
        return await cur.fetchone()

    async def set_icloud_uid(self, task_id: int, uid: str):
        await self.db.execute(
            "UPDATE tasks SET icloud_event_uid=? WHERE id=?",
            (uid, task_id),
        )
        await self.db.commit()

    async def get_uid_tz_dur(self, task_id: int, user_id: int):
        cur = await self.db.execute(
            "SELECT icloud_event_uid, tz, duration_min FROM tasks WHERE id=? AND user_id=?",
            (task_id, user_id),
        )
        return await cur.fetchone()

    async def get_uid_start_tz_dur(self, task_id: int, user_id: int):
        cur = await self.db.execute(
            "SELECT icloud_event_uid, start_utc, tz, duration_min FROM tasks WHERE id=? AND user_id=?",
            (task_id, user_id),
        )
        return await cur.fetchone()

