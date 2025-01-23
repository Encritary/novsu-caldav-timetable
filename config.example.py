from zoneinfo import ZoneInfo

# URL of the CalDAV server
CALDAV_SERVER = "https://calendar.example.com"
# CalDAV user
CALDAV_USER = "user@example.com"
# CalDAV password
CALDAV_PASSWORD = "example"
# CalDAV calendar URL
CALDAV_CALENDAR = "https://calendar.example.com/examplecalendar/"
# CalDAV calendar display name. Used to verify that it's the correct calendar before synchronizing as it could lead
# to data loss
CALDAV_NAME = "Test Calendar"

# NovSU timetable URL
NOVSU_TIMETABLE = "https://portal.novsu.ru/timetableProfile/foo/bar"
# NovSU timezone, most likely should always be Europe/Moscow
NOVSU_TIMEZONE = ZoneInfo('Europe/Moscow')
# NovSU subgroup number, should be None, 1 or 2. If None, parsing both subgroups
NOVSU_SUBGROUP = None
