"""Shelf-life checks for perishable-product transport estimates."""

from math import isfinite


def _validate_days(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be a finite, non-negative number of days.")


def remaining_allowable_travel_time(
    remaining_shelf_life_days: float,
    handling_time_days: float,
    safety_margin_days: float,
) -> float:
    """Return ``shelf life - handling time - safety margin``, in days.

    A negative result means handling plus the safety margin already exceeds
    the remaining shelf life. Preserve that negative value so feasibility
    checks reject every non-negative travel time.
    """
    _validate_days(
        remaining_shelf_life_days=remaining_shelf_life_days,
        handling_time_days=handling_time_days,
        safety_margin_days=safety_margin_days,
    )
    return remaining_shelf_life_days - handling_time_days - safety_margin_days


def is_route_feasible(
    travel_time_days: float,
    remaining_shelf_life_days: float,
    handling_time_days: float,
    safety_margin_days: float,
) -> bool:
    """Check whether travel plus handling fits within usable shelf life.

    All inputs are in days. Equality passes: a route is feasible exactly when
    ``travel_time_days + handling_time_days <= remaining_shelf_life_days -
    safety_margin_days``. Negative or non-finite inputs raise ``ValueError``.
    """
    _validate_days(travel_time_days=travel_time_days)
    allowable_travel_time = remaining_allowable_travel_time(
        remaining_shelf_life_days,
        handling_time_days,
        safety_margin_days,
    )
    return travel_time_days <= allowable_travel_time