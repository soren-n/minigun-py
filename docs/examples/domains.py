"""Bounded domains: float ranges, non-zero integers, dates and strings."""

import datetime
import math
import string

import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop


# -- start: floats --
@context(g.float_range(0.0, 0.25), g.float_range(0.0, 30.0))
@prop("Discount factors lie in the unit interval")
def _discount(rate: float, years: float) -> bool:
    factor = math.exp(-rate * years)
    return 0.0 < factor <= 1.0


# -- end: floats --


# -- start: nonzero --
@context(g.ints(), g.nonzero_int_range(-100, 100))
@prop("Floor division and remainder reconstruct the dividend")
def _divmod(dividend: int, divisor: int) -> bool:
    quotient, remainder = divmod(dividend, divisor)
    return quotient * divisor + remainder == dividend


# -- end: nonzero --


# -- start: dates --
@context(
    g.dates(datetime.date(1990, 1, 1), datetime.date(2040, 12, 31)),
    g.int_range(0, 6),
)
@prop("Rolling forward to a weekday lands on that weekday")
def _roll_forward(day: datetime.date, weekday: int) -> bool:
    rolled = day + datetime.timedelta(days=(weekday - day.weekday()) % 7)
    return rolled.weekday() == weekday and 0 <= (rolled - day).days < 7


# -- end: dates --


# -- start: strings --
@context(g.bounded_strings(1, 5, string.ascii_uppercase))
@prop("Ticker symbols survive a round trip through lower case")
def _ticker(symbol: str) -> bool:
    return symbol.lower().upper() == symbol and 1 <= len(symbol) <= 5


# -- end: strings --

spec = conj(_discount, _divmod, _roll_forward, _ticker)

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
