from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import TripUpdate


@dataclass
class TrackedTrip:
    trip_id: str
    share_token: str
    vehicle_label: str | None
    customer_ref: str | None
    created_at: datetime
    expires_at: datetime
    latest: TripUpdate | None = None
    update_count: int = 0

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class TripStore:
    def __init__(self):
        self._trips = {}
        self._lock = threading.Lock()

    def create(self, trip_id, vehicle_label=None, customer_ref=None):
        now = datetime.now(timezone.utc)
        trip = TrackedTrip(
            trip_id,
            secrets.token_urlsafe(32),
            vehicle_label,
            customer_ref,
            now,
            now + timedelta(hours=24),
        )
        with self._lock:
            self._trips[trip_id] = trip
        return trip

    def apply_update(self, update: TripUpdate):
        with self._lock:
            trip = self._trips.get(update.trip_id)
            if trip is None:
                return None
            if trip.latest:
                update_timestamp = update.updated_at or update.received_at
                latest_timestamp = trip.latest.updated_at or trip.latest.received_at
                if update_timestamp < latest_timestamp:
                    return trip
            trip.latest = update
            trip.update_count += 1
            return trip

    def by_token(self, token):
        with self._lock:
            trip = next(
                (item for item in self._trips.values() if item.share_token == token),
                None,
            )
            return None if trip is None or trip.is_expired else trip

    def purge_expired(self):
        with self._lock:
            keys = [key for key, trip in self._trips.items() if trip.is_expired]
            for key in keys:
                del self._trips[key]
            return len(keys)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trips": len(self._trips),
                "updates": sum(trip.update_count for trip in self._trips.values()),
            }


store = TripStore()
