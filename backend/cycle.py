from calendar import monthrange
from datetime import date, timedelta


DEFAULT_CYCLE_LENGTH = 28
DEFAULT_PERIOD_LENGTH = 5


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def build_calendar(periods, year: int, month: int, today: date | None = None) -> dict:
    today = today or date.today()
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])

    parsed = []
    for period in periods:
        start = date.fromisoformat(period["start_date"])
        complete = bool(period["end_date"])
        end = date.fromisoformat(period["end_date"]) if complete else start
        parsed.append((start, max(start, end), complete))
    parsed.sort()

    starts = sorted({start for start, _, _ in parsed})
    gaps = [
        (current - previous).days
        for previous, current in zip(starts, starts[1:])
        if 21 <= (current - previous).days <= 45
    ]
    lengths = [
        (end - start).days + 1
        for start, end, complete in parsed
        if complete and 1 <= (end - start).days + 1 <= 10
    ]
    cycle_length = round(sum(gaps) / len(gaps)) if gaps else DEFAULT_CYCLE_LENGTH
    period_length = round(sum(lengths) / len(lengths)) if lengths else DEFAULT_PERIOD_LENGTH

    recorded_dates = {
        day.isoformat()
        for start, end, _ in parsed
        for day in _date_range(start, end)
        if month_start <= day <= month_end
    }
    result = {
        "year": year,
        "month": month,
        "has_data": bool(starts),
        "cycle_length": cycle_length,
        "period_length": period_length,
        "current_cycle_day": None,
        "current_phase": "unknown",
        "next_period_start": None,
        "next_fertile_start": None,
        "next_fertile_end": None,
        "recorded_period_dates": sorted(recorded_dates),
        "predicted_period_dates": [],
        "fertile_dates": [],
        "ovulation_dates": [],
    }
    if not starts:
        return result

    anchor = starts[-1]
    next_period = anchor
    while next_period <= today:
        next_period += timedelta(days=cycle_length)

    elapsed = (today - anchor).days
    if elapsed >= 0:
        current_cycle_day = elapsed % cycle_length + 1
        current_cycle_start = today - timedelta(days=current_cycle_day - 1)
        ovulation = current_cycle_start + timedelta(days=max(0, cycle_length - 14))
        fertile_start = ovulation - timedelta(days=5)
        fertile_end = ovulation + timedelta(days=1)
        if current_cycle_day <= period_length:
            current_phase = "period"
        elif fertile_start <= today <= fertile_end:
            current_phase = "ovulation" if today == ovulation else "fertile"
        elif today < fertile_start:
            current_phase = "follicular"
        else:
            current_phase = "luteal"
        result["current_cycle_day"] = current_cycle_day
        result["current_phase"] = current_phase

    fertile_cycle_start = next_period
    next_ovulation = fertile_cycle_start - timedelta(days=14)
    next_fertile_start = next_ovulation - timedelta(days=5)
    next_fertile_end = next_ovulation + timedelta(days=1)
    if next_fertile_end < today:
        fertile_cycle_start += timedelta(days=cycle_length)
        next_ovulation = fertile_cycle_start - timedelta(days=14)
        next_fertile_start = next_ovulation - timedelta(days=5)
        next_fertile_end = next_ovulation + timedelta(days=1)

    result["next_period_start"] = next_period.isoformat()
    result["next_fertile_start"] = next_fertile_start.isoformat()
    result["next_fertile_end"] = next_fertile_end.isoformat()

    predicted_period_dates: set[str] = set()
    fertile_dates: set[str] = set()
    ovulation_dates: set[str] = set()
    cycle_start = anchor
    search_end = month_end + timedelta(days=cycle_length)
    while cycle_start <= search_end:
        if cycle_start > anchor:
            for day in _date_range(
                cycle_start, cycle_start + timedelta(days=period_length - 1)
            ):
                if month_start <= day <= month_end:
                    predicted_period_dates.add(day.isoformat())

        ovulation = cycle_start + timedelta(days=max(0, cycle_length - 14))
        fertile_start = ovulation - timedelta(days=5)
        fertile_end = ovulation + timedelta(days=1)
        for day in _date_range(fertile_start, fertile_end):
            if month_start <= day <= month_end:
                fertile_dates.add(day.isoformat())
        if month_start <= ovulation <= month_end:
            ovulation_dates.add(ovulation.isoformat())
        cycle_start += timedelta(days=cycle_length)

    result["predicted_period_dates"] = sorted(predicted_period_dates - recorded_dates)
    result["fertile_dates"] = sorted(fertile_dates)
    result["ovulation_dates"] = sorted(ovulation_dates)
    return result
