from datetime import datetime
from dateutil import parser as du_parser
import pytz

def parse_user_datetime(text: str, tz_str: str) -> datetime | None:
    try:
        dt = du_parser.parse(text, dayfirst=True, fuzzy=True)
    except Exception:
        return None
    tz = pytz.timezone(tz_str)
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt.astimezone(pytz.utc)
