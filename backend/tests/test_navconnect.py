def test_dry_run_does_not_post(monkeypatch):
    import app.navconnect as navconnect
    import uuid

    monkeypatch.setattr(navconnect.config, "DRY_RUN", True)

    trip_id = str(uuid.uuid4())
    result = navconnect.create_trip(
        trip_id, "android-app", "ios-app", pubsub_field_mask="execution.remainingRoute"
    )

    assert result["dry_run"] is True
    assert result["trip_id"] == trip_id
    assert result["request_body_preview"] == {
        "config": {
            "enablePubsub": True,
            "pubsubFieldMask": "execution.remainingRoute",
        },
        "androidAppId": "android-app",
        "iosAppId": "ios-app",
    }


def test_create_trip_rejects_non_uuid_without_network(monkeypatch):
    import app.navconnect as navconnect

    monkeypatch.setattr(
        navconnect.config, "DRY_RUN", False
    )

    def unexpected_network_call(*args, **kwargs):
        raise AssertionError("network must not be called")

    monkeypatch.setattr("requests.post", unexpected_network_call, raising=False)

    import pytest

    with pytest.raises(navconnect.NavConnectError, match="RFC-4122 UUID"):
        navconnect.create_trip("nesamone")


def test_dry_run_trip_id_is_uuid(monkeypatch):
    import uuid
    import app.navconnect as navconnect

    monkeypatch.setattr(navconnect.config, "DRY_RUN", True)
    trip_id = str(uuid.uuid4())

    result = navconnect.create_trip(trip_id)

    assert "request_body_preview" in result
    uuid.UUID(result["trip_id"])
