from datetime import timezone

from app.models import TripUpdate


def test_execution_position_is_primary_and_fallback_is_supported():
    update = TripUpdate.from_payload(
        {
            "execution": {
                "location": {
                    "point": {"latitude": 51.5, "longitude": -0.12}
                }
            },
            "lastLocation": {
                "latLng": {"latitude": 1.2, "longitude": 3.4}
            },
        }
    )
    fallback = TripUpdate.from_payload(
        {"lastLocation": {"latLng": {"latitude": 1.2, "longitude": 3.4}}}
    )

    assert (update.latitude, update.longitude) == (51.5, -0.12)
    assert (fallback.latitude, fallback.longitude) == (1.2, 3.4)


def test_unknown_and_raw():
    payload = {"tripId": "x", "mystery": 7}
    update = TripUpdate.from_payload(payload)

    assert update.raw is payload
    assert "mystery" in update.unknown_fields


def test_execution_source_time_is_primary_and_public_iso_string():
    update = TripUpdate.from_payload(
        {
            "execution": {
                "location": {
                    "sourceTime": "2026-08-11T18:05:00Z",
                    "serverTime": "2026-08-11T18:06:00Z",
                }
            }
        }
    )
    assert update.updated_at.tzinfo == timezone.utc
    assert update.to_public_dict()["updated_at"] == "2026-08-11T18:05:00+00:00"


def test_public_excludes_private_fields():
    public = TripUpdate.from_payload(
        {"tripId": "secret", "latitude": 1, "longitude": 2}
    ).to_public_dict()

    assert "raw" not in public
    assert "trip_id" not in public


def test_execution_duration_and_computed_eta():
    update = TripUpdate.from_payload(
        {
            "name": "projects/123456/trips/trip-1",
            "execution": {
                "location": {
                    "sourceTime": "2025-05-30T12:37:26Z",
                    "point": {"latitude": 51.5333329, "longitude": -0.1265845},
                },
                "remainingDuration": "990s",
                "remainingDistanceMeters": 2879,
            },
        }
    )
    public = update.to_public_dict()

    assert update.remaining_duration_seconds == 990
    assert update.remaining_distance_meters == 2879
    assert public["eta"] == "2025-05-30T12:53:56+00:00"
    assert public["eta_is_computed"] is True


def test_duration_compound_string_and_numeric_fallback():
    assert TripUpdate.from_payload(
        {"execution": {"remainingDuration": "1h2m3s"}}
    ).remaining_duration_seconds == 3723
    assert TripUpdate.from_payload(
        {"remainingDurationSeconds": 61.7}
    ).remaining_duration_seconds == 61


def test_real_eta_is_not_marked_computed():
    update = TripUpdate.from_payload(
        {
            "execution": {
                "location": {"sourceTime": "2025-05-30T12:37:26Z"},
                "remainingDuration": "990s",
            },
            "eta": "2025-05-30T13:00:00Z",
        }
    )

    assert update.to_public_dict()["eta"] == "2025-05-30T13:00:00+00:00"
    assert update.to_public_dict()["eta_is_computed"] is False


def test_missing_eta_is_public_none():
    public = TripUpdate.from_payload({}).to_public_dict()
    assert public["eta"] is None
    assert public["eta_is_computed"] is False


def test_unwraps_createdTrip_envelope():
    payload = {
        "createdTrip": {
            "name": "projects/461566048811/trips/23d0f372-1b60-484a-9e16-6bfb4e1221ae",
            "state": "NEW",
            "execution": {},
        }
    }
    update = TripUpdate.from_payload(payload)
    assert update.trip_id == "23d0f372-1b60-484a-9e16-6bfb4e1221ae"
    assert update.state == "NEW"


def test_unwraps_updatedTrip_envelope():
    payload = {
        "updatedTrip": {
            "name": "projects/461566048811/trips/abc-123",
            "state": "ACTIVE",
            "execution": {
                "location": {"point": {"latitude": 54.68, "longitude": 25.28}},
            },
        }
    }
    update = TripUpdate.from_payload(payload)
    assert update.trip_id == "abc-123"
    assert update.latitude == 54.68
    assert update.longitude == 25.28


def test_unknown_wrapper_key_falls_back_to_generic_unwrap():
    payload = {"endedTrip": {"name": "projects/1/trips/zzz", "state": "COMPLETE"}}
    update = TripUpdate.from_payload(payload)
    assert update.trip_id == "zzz"


def test_no_envelope_still_works_unchanged():
    payload = {"name": "projects/1/trips/direct-id", "state": "NEW"}
    update = TripUpdate.from_payload(payload)
    assert update.trip_id == "direct-id"
