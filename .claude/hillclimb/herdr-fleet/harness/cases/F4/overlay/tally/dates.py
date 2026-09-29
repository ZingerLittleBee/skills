"""Date helpers for upcoming period reports."""

import datetime as dt


def month_key(date: str) -> str:
    """Return the `YYYY-MM` month of an ISO date."""
    return date[:7]


def week_of(date: str) -> str:
    """Return the ISO week of a date as `YYYY-Www`."""
    d = dt.date.fromisoformat(date)
    return f"{d.year}-W{d.isocalendar()[1]:02d}"
