from datetime import datetime, timedelta, timezone

from app.models import TripUpdate
from app.store import TripStore


def test_older_update_does_not_overwrite():
    store = TripStore()
    store.create("x")
    store.apply_update(
        TripUpdate.from_payload({"tripId": "x", "latitude": 2, "updateTime": 20})
    )
    store.apply_update(
        TripUpdate.from_payload({"tripId": "x", "latitude": 1, "updateTime": 10})
    )

    assert store._trips["x"].latest.latitude == 2


def test_nested_older_update_does_not_overwrite_newer_position():
    store = TripStore()
    store.create("x")
    store.apply_update(
        TripUpdate.from_payload(
            {
                "tripId": "x",
                "lastLocation": {
                    "latLng": {"latitude": 52.4102, "longitude": 4.0},
                    "updateTime": "2026-08-11T18:05:00Z",
                },
            }
        )
    )
    store.apply_update(
        TripUpdate.from_payload(
            {
                "tripId": "x",
                "latitude": 0.0,
                "updateTime": "2026-08-11T17:00:00Z",
            }
        )
    )

    assert store._trips["x"].latest.latitude == 52.4102


def test_received_at_protects_updates_without_update_time():
    store = TripStore()
    store.create("x")
    newer = TripUpdate(
        trip_id="x",
        latitude=52.4102,
        received_at=datetime(2026, 8, 11, 18, 5, tzinfo=timezone.utc),
    )
    older = TripUpdate(
        trip_id="x",
        latitude=0.0,
        received_at=datetime(2026, 8, 11, 17, tzinfo=timezone.utc),
    )
    store.apply_update(newer)
    store.apply_update(older)

    assert store._trips["x"].latest.latitude == 52.4102


def test_newer_update_overwrites_older_update():
    store = TripStore()
    store.create("x")
    store.apply_update(
        TripUpdate.from_payload(
            {
                "tripId": "x",
                "latitude": 1.0,
                "updateTime": "2026-08-11T17:00:00Z",
            }
        )
    )
    store.apply_update(
        TripUpdate.from_payload(
            {
                "tripId": "x",
                "latitude": 2.0,
                "updateTime": "2026-08-11T18:05:00Z",
            }
        )
    )

    assert store._trips["x"].latest.latitude == 2.0


def test_expired_token_and_purge():
    store = TripStore()
    trip = store.create("x")
    trip.expires_at -= timedelta(hours=25)

    assert store.by_token(trip.share_token) is None
    assert store.purge_expired() == 1
    assert store.stats()["trips"] == 0
