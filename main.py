from datetime import timedelta, timezone

import caldav

import config
import novsu_parser


def main() -> None:
    # Initialize CalDAV client
    with caldav.DAVClient(
        url=config.CALDAV_SERVER,
        username=config.CALDAV_USER,
        password=config.CALDAV_PASSWORD
    ) as client:
        # Get the calendar by its URL from config
        calendar = client.calendar(url=config.CALDAV_CALENDAR)

        # Verify its display name
        calendar_name = calendar.get_display_name()
        if calendar_name != config.CALDAV_NAME:
            raise RuntimeError(f"Mismatched calendar name. Expected {config.CALDAV_NAME}, got {calendar_name}")

        # Parse NovSU timetable
        print("Parsing NovSU timetable...")
        timetable = novsu_parser.parse_timetable(config.NOVSU_TIMETABLE, config.NOVSU_TIMEZONE, config.NOVSU_SUBGROUP)

        print(f"Parsed timetable from {timetable.dt_from.strftime('%Y-%m-%d')} to "
              f"{timetable.dt_to.strftime('%Y-%m-%d')}, got {len(timetable.lessons)} lessons")

        # Purge existing events to put the new ones on their place
        existing_events = calendar.search(start=timetable.dt_from, end=timetable.dt_to)
        for i, event in enumerate(existing_events):
            print(f"Deleting existing events... ({i} / {len(existing_events)})")

            event.delete()

        print(f"Deleted {len(existing_events)} existing events")

        # Import all the lesson events that were parsed from NovSU timetable
        for i, lesson in enumerate(timetable.lessons):
            print(f"Importing lessons... ({i} / {len(timetable.lessons)})")

            # Make a description from lesson properties
            description = [
                f"Преподаватель: {lesson.teacher}"
            ]
            if lesson.subgroup:
                description.append(f"Подгруппа: {lesson.subgroup}")
            if lesson.comment:
                description.append(f"Комментарий: {lesson.comment}")

            # EXDATEs should be UTC as no timezone is specified in ICS
            exdates = [exc_dt.astimezone(timezone.utc) for exc_dt in lesson.exceptions]

            # Create a corresponding event
            ev = calendar.save_event(
                dtstart=lesson.dt_first,
                dtend=lesson.dt_first + timedelta(minutes=45),
                summary=lesson.subject,
                description="\n".join(description),
                location=lesson.location,
                rrule={
                    'FREQ': 'WEEKLY',
                    'INTERVAL': lesson.interval_weeks,
                    'UNTIL': lesson.date_until,
                }
            )
            # Workaround for some calendars that don't allow to put a few exdates on event creation
            for exdate in exdates:
                ev.icalendar_component.add('exdate', exdate)
            ev.save()

        print(f"Imported {len(timetable.lessons)} lessons")


if __name__ == '__main__':
    main()
