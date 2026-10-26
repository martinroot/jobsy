"""Paid package accounting for jobsy orders.

One package unit = one deliverable (e.g. 1000 characters of text).
The balance is only debited when a result is delivered.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Package:
    unit: str          # e.g. "1000 знаков"
    paid: int          # units paid
    used: int          # units used
    remaining: int     # paid - used

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def can_deliver(self, units_needed: int = 1) -> bool:
        return self.remaining >= units_needed

    def debit(self, units: int) -> "Package":
        if not self.can_deliver(units):
            raise ValueError("package exhausted")
        return Package(
            unit=self.unit,
            paid=self.paid,
            used=self.used + units,
            remaining=self.remaining - units,
        )

    def to_dict(self) -> dict:
        return {
            "unit": self.unit,
            "paid": self.paid,
            "used": self.used,
            "remaining": self.remaining,
            "rule": "Остаток списывается только за выданные результаты.",
        }


def package_from_state(state: dict) -> Package | None:
    q = state.get("package") or state.get("quota")
    if not q:
        return None
    return Package(
        unit=str(q.get("unit", "единиц")),
        paid=int(q.get("paid", 0)),
        used=int(q.get("used", 0)),
        remaining=int(q.get("remaining", q.get("paid", 0) - q.get("used", 0))),
    )
