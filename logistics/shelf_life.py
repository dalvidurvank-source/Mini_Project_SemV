"""Shelf-life checks for perishable-product transport estimates."""

from math import isfinite, isclose
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

INDIA = ZoneInfo('Asia/Kolkata')
# Explicit project delivery-planning budgets, not validated spoilage predictions.
CONDITIONS = {
    'firm_ripe': {'label':'Firm ripe, kept shaded', 'hours':48},
    'very_ripe': {'label':'Very ripe / soft, needs quick sale', 'hours':24},
    'unknown': {'label':'Condition or storage uncertain', 'hours':24},
    'damaged': {'label':'Visible spoilage / damaged lot', 'hours':0},
}


def india_now():
    return datetime.now(INDIA)


def policy():
    return {'crop':'Tomato', 'conditions':[{'id':k, **v} for k,v in CONDITIONS.items()],
            'handling_hours':2, 'safety_margin_hours':4, 'warning_slack_hours':6,
            'version':'tomato-delivery-planning-v1',
            'notice':'These are conservative project planning budgets, not measured expiry times or food-safety certification. Temperature, maturity and damage can shorten usable life. Cooling does not automatically extend this budget.',
            'background_source':'https://ucanr.edu/sites/default/files/2019-09/311224.pdf'}


def assess_delivery(payload, travel_hours, trips=1, empty_return_factor=1, now=None):
    """Use actual lot dates (not historical forecast dates) and last-trip delivery.

    Date-only harvests count from midnight conservatively. A selected selling
    date is the earliest pickup day; explicit pickup_at uses India local time.
    """
    now = now or india_now()
    if now.tzinfo is None:
        raise ValueError('The evaluation clock must include a timezone.')
    now = now.astimezone(INDIA)
    if payload.get('crop','Tomato') != 'Tomato':
        raise ValueError('A delivery-life policy is currently available only for Tomato.')
    condition = payload.get('produce_condition','firm_ripe')
    if not isinstance(condition,str) or condition not in CONDITIONS:
        raise ValueError('Choose a supported crop condition.')
    harvest_time = payload.get('harvest_time') or '00:00'
    try:
        if len(harvest_time) != 5:
            raise ValueError()
        harvested = datetime.fromisoformat(f"{payload['harvest_date']}T{harvest_time}").replace(tzinfo=INDIA)
        if harvested > now:
            raise ValueError('Harvest time cannot be in the future.')
        selling_date = datetime.strptime(payload.get('selling_date') or now.date().isoformat(),'%Y-%m-%d').date()
        if selling_date < now.date():
            raise ValueError('Pickup/selling date cannot be in the past.')
        departure = max(now, datetime.combine(selling_date,time.min,tzinfo=INDIA))
        if payload.get('pickup_at'):
            raw = payload['pickup_at']
            pickup = datetime.fromisoformat(raw)
            pickup = pickup.replace(tzinfo=INDIA) if pickup.tzinfo is None else pickup.astimezone(INDIA)
            if pickup < now - timedelta(minutes=1):
                raise ValueError('Planned pickup time is in the past. Choose a future time or clear it for immediate pickup.')
            if pickup.date() < selling_date:
                raise ValueError('Planned pickup cannot precede the expected selling date.')
            departure = max(now, pickup)
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError(f'Check harvest and pickup dates/times. {exc}') from exc
    if isinstance(trips,bool) or not isinstance(trips,int) or trips < 1:
        raise ValueError('Trip count must be a positive integer.')
    if isinstance(travel_hours,bool) or not isfinite(travel_hours) or travel_hours < 0:
        raise ValueError('Road travel time must be finite and non-negative.')
    if not isfinite(empty_return_factor) or not 0 <= empty_return_factor <= 1:
        raise ValueError('Empty-return factor must be between 0 and 1.')
    settings = policy()
    budget = CONDITIONS[condition]['hours']
    age = (now - harvested).total_seconds()/3600
    waiting = (departure-now).total_seconds()/3600
    # One vehicle makes sequential trips; the last batch waits for earlier returns.
    prior_trips = (trips-1)*(travel_hours*(1+empty_return_factor)+settings['handling_hours'])
    handling = settings['handling_hours']
    margin = settings['safety_margin_hours']
    slack = budget-age-waiting-prior_trips-travel_hours-handling-margin
    feasible = is_route_feasible((travel_hours+prior_trips)/24, max(0,budget-age-waiting)/24,
                                 handling/24, margin/24) and age+waiting <= budget
    if condition == 'damaged':
        status, reason = 'blocked','This lot is marked damaged or visibly spoiled. Do not offer it for sale through this flow.'
    elif not feasible:
        status, reason = 'blocked','Estimated delivery exceeds the usable planning window after harvest age, waiting, handling and the safety margin.'
    elif slack <= settings['warning_slack_hours'] or condition in ('very_ripe','unknown'):
        status, reason = 'warning','Limited delivery buffer or uncertain crop condition. Confirm the lot condition and pickup timing before preparing a sale.'
    else:
        status, reason = 'eligible','Estimated delivery fits within the configured planning window.'
    return {'status':status, 'can_select':status in ('eligible','warning'), 'requires_acknowledgment':status=='warning',
            'reason':reason, 'policy_version':settings['version'], 'condition':condition,
            'condition_label':CONDITIONS[condition]['label'], 'planning_budget_hours':budget,
            'harvested_at':harvested.isoformat(), 'evaluated_at':now.isoformat(),
            'pickup_at':departure.isoformat(),
            'estimated_last_delivery_at':(departure+timedelta(hours=prior_trips+travel_hours+handling)).isoformat(),
            'harvest_age_hours':round(age,3), 'waiting_hours':round(waiting,3),
            'prior_trips_hours':round(prior_trips,3), 'road_travel_hours':round(travel_hours,3),
            'handling_hours':handling, 'safety_margin_hours':margin, 'slack_hours':round(slack,3),
            'date_only_harvest':not bool(payload.get('harvest_time')), 'trips':trips,
            'notice':settings['notice']}


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
    return allowable_travel_time >= 0 and (travel_time_days <= allowable_travel_time or
                                         isclose(travel_time_days,allowable_travel_time,rel_tol=0,abs_tol=1e-9))
