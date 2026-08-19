from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from typing import Any


def _dig(payload: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = payload
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                break
            current = current[part]
        else:
            return current
    return None


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            stripped = value.strip()
            suffix = "+00:00" if stripped.endswith("Z") else ""
            parsed = datetime.fromisoformat(stripped.removesuffix("Z") + suffix)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (OverflowError, TypeError, ValueError):
        return None


def _duration_seconds(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (OverflowError, TypeError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?\s*", value
    )
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


@dataclass
class TripUpdate:
    trip_id: str | None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    remaining_distance_meters: int | None = None
    remaining_duration_seconds: int | None = None
    eta: datetime | None = None
    eta_is_computed: bool = False
    updated_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    unknown_fields: list[str] = field(default_factory=list)
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TripUpdate":
        lat = (
            "execution.location.point.latitude",
            "lastLocation.latLng.latitude",
            "lastLocation.latitude",
            "location.latLng.latitude",
            "currentLocation.latLng.latitude",
            "vehicleLocation.latLng.latitude",
            "latitude",
            "lat",
            "last_location.lat_lng.latitude",
            "last_location.latitude",
        )
        lng = (
            "execution.location.point.longitude",
            "lastLocation.latLng.longitude",
            "lastLocation.longitude",
            "location.latLng.longitude",
            "currentLocation.latLng.longitude",
            "vehicleLocation.latLng.longitude",
            "longitude",
            "lng",
            "lon",
            "last_location.lat_lng.longitude",
            "last_location.longitude",
        )
        name = _dig(payload, "name")
        trip_id = _dig(payload, "tripId", "trip_id", "id")
        if trip_id is None and isinstance(name, str):
            trip_id = name.rstrip("/").rsplit("/", 1)[-1]
        known = {
            "name",
            "tripId",
            "trip_id",
            "id",
            "state",
            "tripStatus",
            "trip_status",
            "status",
            "lastLocation",
            "last_location",
            "location",
            "currentLocation",
            "current_location",
            "vehicleLocation",
            "vehicle_location",
            "latitude",
            "longitude",
            "lat",
            "lng",
            "lon",
            "remainingDistanceMeters",
            "remaining_distance_meters",
            "execution",
            "remainingDurationSeconds",
            "remaining_duration_seconds",
            "etaToDestination",
            "eta_to_destination",
            "eta",
            "estimatedArrivalTime",
            "updateTime",
            "update_time",
        }
        updated_at = _timestamp(
            _dig(
                payload,
                "execution.location.sourceTime",
                "execution.location.serverTime",
                "lastLocation.updateTime",
                "last_location.update_time",
                "location.updateTime",
                "currentLocation.updateTime",
                "vehicleLocation.updateTime",
                "updateTime",
                "update_time",
            )
        )
        eta = _timestamp(
            _dig(
                payload,
                "etaToDestination",
                "eta_to_destination",
                "eta",
                "estimatedArrivalTime",
            )
        )
        duration = _duration_seconds(
            _dig(
                payload,
                "execution.remainingDuration",
                "remainingDurationSeconds",
                "remaining_duration_seconds",
            )
        )
        update = cls(
            str(trip_id) if trip_id is not None else None,
            _dig(payload, "state", "tripStatus", "trip_status", "status"),
            _dig(payload, *lat),
            _dig(payload, *lng),
            _number(
                _dig(
                    payload,
                    "execution.remainingDistanceMeters",
                    "remainingDistanceMeters",
                    "remaining_distance_meters",
                )
            ),
            duration,
            eta,
            False,
            updated_at,
            payload,
            [key for key in payload if key not in known],
        )
        if update.eta is None and duration is not None:
            update.eta = (updated_at or update.received_at) + timedelta(
                seconds=duration
            )
            update.eta_is_computed = True
        return update

    @property
    def has_position(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "remaining_distance_meters": self.remaining_distance_meters,
            "remaining_duration_seconds": self.remaining_duration_seconds,
            "eta": self.eta.isoformat() if self.eta else None,
            "eta_is_computed": self.eta_is_computed,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
