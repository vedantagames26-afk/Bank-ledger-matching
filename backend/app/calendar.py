from datetime import date, timedelta
from dataclasses import dataclass, field


@dataclass
class BusinessCalendar:
    holidays: dict = field(default_factory=dict)
    weekends: tuple = (5, 6)

    def working(self, day: date) -> bool:
        holiday = self.holidays.get(day.isoformat(), {})
        return day.weekday() not in self.weekends and not (
            holiday.get("verified")
            and holiday.get("source")
            and holiday.get("verified_at")
        )

    def add(self, day: date, count: int) -> date:
        while count:
            day += timedelta(days=1)
            if self.working(day):
                count -= 1
        return day

    def difference(self, start: date, end: date) -> int:
        sign = 1 if end >= start else -1
        a, b = sorted((start, end))
        total = 0
        while a < b:
            a += timedelta(days=1)
            total += self.working(a)
        return sign * total
