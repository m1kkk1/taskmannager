from datetime import datetime, timedelta
from icalendar import Calendar, Event
import pytz

def build_ics(tasks, filename: str) -> str:
    cal = Calendar()
    cal.add('prodid', '-//TaskPlannerBot//')
    cal.add('version', '2.0')
    for title, s_utc, dur, tz in tasks:
        start = datetime.fromisoformat(s_utc).astimezone(pytz.timezone(tz))
        end = start + timedelta(minutes=int(dur))
        ev = Event()
        ev.add('summary', title)
        ev.add('dtstart', start)
        ev.add('dtend', end)
        ev.add('tzid', tz)
        cal.add_component(ev)
    with open(filename, 'wb') as f:
        f.write(cal.to_ical())
    return filename
