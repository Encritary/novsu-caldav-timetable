import re
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from http import HTTPStatus
from typing import Optional
from zoneinfo import ZoneInfo

import bs4
import requests

EXPECTED_HEADER = ["дата", "время", "подгр.", "предмет", "преподаватель", "ауд.", "комм."]
DAYS_OF_WEEK = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@dataclass
class Lesson:
    dt_first: datetime
    date_until: date
    subject: str
    teacher: str
    location: str
    interval_weeks: int
    subgroup: Optional[int]
    exceptions: list[datetime]
    comment: str


@dataclass
class Timetable:
    dt_from: date
    dt_to: date
    lessons: list[Lesson]


def parse_timetable(timetable_url: str, timezone: ZoneInfo, my_subgroup: Optional[int] = None) -> Timetable:
    # Doing an HTTP request
    response = requests.get(timetable_url)
    if response.status_code != HTTPStatus.OK:
        raise RuntimeError(f"NovSU timetable returned non-OK http code: {response.status_code}")

    # Parsing timetable page with BS4
    html = bs4.BeautifulSoup(response.text, 'html5lib')

    # Parsing the title of timetable
    title: str = html.find('h3').text
    # The title contains the dates on which the timetable is valid
    regex_dates = re.search(r'с\s+(\d+\.\d+\.\d+)\s+по\s+(\d+\.\d+\.\d+)', title)
    if regex_dates is None:
        raise RuntimeError("Format of the title has changed")

    # Parsing dates as datetime objects
    timetable_from = datetime.strptime(regex_dates.group(1), '%d.%m.%Y').date()
    timetable_to = datetime.strptime(regex_dates.group(2), '%d.%m.%Y').date()
    timetable_to += timedelta(days=1)  # inclusive -> exclusive

    # Find the table itself
    table = html.find('table', attrs={'class': 'shedultable'})

    # Parse table contents
    expect_lessons = 0  # Firstly we expect the name of day of the week, then N lessons
    weekday = -1  # Current day of week (0 = Monday)

    prev_hours = None  # Hours of previous rows, hours column is merged for some rows

    # Resulting list of Lesson objects
    lessons: list[Lesson] = []

    row: bs4.element.Tag
    for i, row in enumerate(table.find_all('tr')):
        if i == 0:
            # First row is always the table header, check that it hasn't changed
            table_header = row.text.strip().split()
            if table_header != EXPECTED_HEADER:
                raise RuntimeError("Table header has changed")

            continue

        if expect_lessons == 0:  # We expect a day of the week
            cell: bs4.element.Tag = row.find('td')
            # Cell should contain a name of day of the week in Russian
            dow_name = cell.find('b').text

            if dow_name not in DAYS_OF_WEEK:
                raise RuntimeError(f"Unknown day of week: {dow_name}")

            weekday = DAYS_OF_WEEK.index(dow_name)  # Converting Russian name of DoW to a number
            expect_lessons = int(cell.attrs['rowspan']) - 1  # Now we expect rowspan-1 rows with lessons

            continue

        # Parse a lesson
        expect_lessons -= 1

        # Get a list of all cells of the row
        cells: list[bs4.element.Tag] = list(row.find_all('td'))

        has_hours = (len(cells) == 6)  # If row has 6 cells, then it has its own cell with hours

        if has_hours:
            hours = cells.pop(0).get_text(separator=' ', strip=True).split()
            prev_hours = hours
        else:
            # Otherwise, we expect hours to be spanned for a few rows, so we take previous hours
            hours = prev_hours

            if hours is None:
                raise RuntimeError("No hours column for row")

        # Subgroup is expected to be empty, "1)" or "2)". Some lessons are split are conducted in subgroups
        subgroup = cells[0].get_text(strip=True).rstrip(')')
        if len(subgroup) > 0:
            subgroup = int(subgroup)

            if my_subgroup is not None and subgroup != my_subgroup:
                # Skip others' subgroup lessons
                continue
        else:
            subgroup = None

        # Parse subject's name
        subject = cells[1].get_text(separator=" ", strip=True)
        if subject[0] != '(':
            # This can be considered as a note, not a subject
            continue

        # Parse other cells
        teacher = cells[2].get_text(separator=" ", strip=True)
        location = cells[3].get_text(separator=" ", strip=True)
        if location == ".":  # A dot is empty location
            location = None
        comment = cells[4].get_text(separator=" ", strip=True)

        # Date on which the first lesson is
        lesson_first = timetable_from + timedelta(days=(weekday - timetable_from.weekday()) % 7)
        lesson_until = timetable_to  # Date on which this lessons end
        interval_weeks = 1  # How often will this lesson be

        # Parse comment
        comment = re.sub(r'\s+', ' ', comment)  # Replace multiple spaces with one
        if location is None and "ДОТ" in comment:
            # This is considered to be an online-course class
            continue

        exceptions: list[date] = []  # Days when this lesson is skipped
        exc_match = re.search(r'((?:\d+\.\d+\s*[;,и\s]*)+) занятий не будет', comment)
        if exc_match is not None:
            dates_list = exc_match.group(1)
            dates_strs = re.findall(r'\d+\.\d+', dates_list)

            exceptions = [datetime.strptime(f"{date_str}.{timetable_from.year}", '%d.%m.%Y').date()
                          for date_str in dates_strs]

        from_match = re.search(r'с (\d+\.\d+)', comment)
        if from_match is not None:
            date_str = from_match.group(1)
            lesson_first = datetime.strptime(f"{date_str}.{timetable_from.year}", '%d.%m.%Y').date()

            # Check if this overlaps with previous lesson row
            if subgroup is None and not has_hours:
                for prev_lesson in lessons[-len(hours):]:
                    if prev_lesson.date_until == timetable_to:
                        # They assumed that current lesson replaces previous one on given date
                        prev_lesson.date_until = lesson_first

        to_match = re.search(r'(?:по|до) (\d+\.\d+)', comment)
        if to_match is not None:
            date_str = to_match.group(1)
            lesson_until = datetime.strptime(f"{date_str}.{timetable_from.year}", '%d.%m.%Y').date()
            lesson_until += timedelta(days=1)  # inclusive -> exclusive

        if "неделе" in comment:  # only on "upper" or "lower" weeks
            # first week is always the upper week
            lesson_from_upper = (lesson_first.isocalendar().week - timetable_from.isocalendar().week) % 2 == 0

            on_upper = ("по верхней неделе" in comment)
            if on_upper != lesson_from_upper:
                lesson_first += timedelta(weeks=1)

            interval_weeks = 2

        # Each hour gives us a separate lesson event
        for clock in hours:
            # Parse lesson time with the given timezone
            lesson_time = datetime.strptime(clock, '%H:%M').replace(tzinfo=timezone).time()
            # Append resulting lesson object to the list
            lessons.append(Lesson(
                dt_first=datetime.combine(lesson_first, lesson_time),
                date_until=lesson_until,
                subject=subject,
                teacher=teacher,
                location=location,
                interval_weeks=interval_weeks,
                subgroup=subgroup,
                exceptions=[datetime.combine(exdate, lesson_time) for exdate in exceptions],
                comment=comment
            ))

    # Return the Timetable object, containing its date boundaries and all the lesson objects
    return Timetable(
        dt_from=timetable_from,
        dt_to=timetable_to,
        lessons=lessons
    )
