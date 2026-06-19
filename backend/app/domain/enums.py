from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"


class Visibility(StrEnum):
    PRIVATE = "private"  # owner + members of the owner's groups
    PUBLIC = "public"  # everyone (admin-uploaded corpus)


class DemoSource(StrEnum):
    UPLOAD = "upload"
    HLTV = "hltv"


class DemoStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"


class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Side(StrEnum):
    T = "T"
    CT = "CT"


class UtilityType(StrEnum):
    SMOKE = "smoke"
    FLASH = "flash"
    MOLOTOV = "molotov"
    HE = "he"


class BuyType(StrEnum):
    ECO = "eco"
    FORCE = "force"
    FULL = "full"


class Site(StrEnum):
    A = "A"
    B = "B"
    MID = "Mid"
    NO_PLANT = "NoPlant"


class Region(StrEnum):
    A = "A"
    B = "B"
    MID = "Mid"


class DateRange(StrEnum):
    LAST_MONTH = "last_month"
    LAST_3_MONTHS = "last_3_months"
    LAST_6_MONTHS = "last_6_months"
    LAST_12_MONTHS = "last_12_months"

    @property
    def days(self) -> int:
        return {
            DateRange.LAST_MONTH: 30,
            DateRange.LAST_3_MONTHS: 90,
            DateRange.LAST_6_MONTHS: 180,
            DateRange.LAST_12_MONTHS: 365,
        }[self]

    def start_date(self, today: date) -> date:
        return today - timedelta(days=self.days)
