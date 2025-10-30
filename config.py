# app/config.py
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Settings:
    bot_token: str = "8216236995:AAFgfURWQL8JpUhsBzG-jfxgkcgc3J-HrJU"  # <<< замените здесь
    default_tz: str = "Europe/Kyiv"
    log_level: str = "INFO"
    db_path: Path = Path(__file__).resolve().parent.parent / "taskplanner.db"
    default_remind_min: int = 15
    icloud_user: str | None = "nbumaznyj@gmail.com"
    icloud_app_password: str | None = "uciy-hxxj-oygz-ydpc"
    icloud_calendar_name: str = "TaskPlanner"
    export_limit: int = 50
    list_limit: int = 20
    scheduler_timezone: str | None = None

    @property
    def icloud_available(self) -> bool:
        return bool(self.icloud_user and self.icloud_app_password)

settings = Settings
