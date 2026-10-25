"""Calculate great-circle distances between GPS coordinates."""

from math import atan2, cos, isfinite, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0


def _validate_coordinate(latitude: float, longitude: float) -> None:
    if not isfinite(latitude) or not isfinite(longitude):
        raise ValueError("Latitude and longitude must be finite numbers.")
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("Longitude must be between -180 and 180 degrees.")


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Return the great-circle distance between two points in kilometres.

    The Haversine formula converts each coordinate to radians, then computes
    ``a = sin²(Δlat/2) + cos(lat1) cos(lat2) sin²(Δlon/2)`` and
    ``c = 2 atan2(sqrt(a), sqrt(1-a))`` and ``distance = R*c``, using
    Earth's mean radius ``R = 6371 km``.
    """
    _validate_coordinate(lat1, lon1)
    _validate_coordinate(lat2, lon2)

    latitude_1 = radians(lat1)
    latitude_2 = radians(lat2)
    latitude_delta = radians(lat2 - lat1)
    longitude_delta = radians(lon2 - lon1)

    haversine_value = (
        sin(latitude_delta / 2.0) ** 2
        + cos(latitude_1) * cos(latitude_2) * sin(longitude_delta / 2.0) ** 2
    )
    # Clamp a to [0, 1] to protect the square roots from floating-point rounding.
    haversine_value = min(1.0, max(0.0, haversine_value))
    central_angle = 2.0 * atan2(
        sqrt(haversine_value),
        sqrt(1.0 - haversine_value),
    )
    return EARTH_RADIUS_KM * central_angle