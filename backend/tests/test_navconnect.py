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


def test_get_access_token_falls_back_to_gcloud_cli(monkeypatch):
    import subprocess
    import app.navconnect as navconnect

    def broken_adc(*args, **kwargs):
        raise Exception("no ADC found")

    monkeypatch.setattr("google.auth.default", broken_adc, raising=False)

    class FakeCompletedProcess:
        stdout = "fake-cli-token\n"

    def fake_run(*args, **kwargs):
        assert args[0][:2] == ["gcloud", "auth"]
        return FakeCompletedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)

    token, project = navconnect._get_access_token()
    assert token == "fake-cli-token"
    assert project is None


def test_get_access_token_raises_when_both_paths_fail(monkeypatch):
    import subprocess
    import pytest
    import app.navconnect as navconnect

    def broken_adc(*args, **kwargs):
        raise Exception("no ADC found")

    monkeypatch.setattr("google.auth.default", broken_adc, raising=False)

    def broken_cli(*args, **kwargs):
        raise FileNotFoundError("gcloud not installed")

    monkeypatch.setattr(subprocess, "run", broken_cli)

    with pytest.raises(navconnect.NavConnectError, match="gcloud CLI fallback failed"):
        navconnect._get_access_token()


def test_create_trip_real_call_uses_bearer_token(monkeypatch):
    import app.navconnect as navconnect
    import uuid

    monkeypatch.setattr(navconnect.config, "DRY_RUN", False)
    monkeypatch.setattr(
        navconnect, "_get_access_token", lambda: ("tok-123", "quota-proj")
    )

    captured = {}

    class FakeResponse:
        ok = True

        def json(self):
            return {
                "name": "projects/p/trips/x",
                "authToken": {"token": "real-action-token"},
            }

    def fake_post(url, json, params, headers, timeout):
        captured["headers"] = headers
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr("requests.post", fake_post)

    trip_id = str(uuid.uuid4())
    result = navconnect.create_trip(
        trip_id,
        destination_lat=1.0,
        destination_lng=2.0,
    )

    assert result["dry_run"] is False
    assert captured["headers"]["Authorization"] == "Bearer tok-123"
    assert captured["headers"]["X-Goog-User-Project"] == "quota-proj"
    assert "real-action-token" in result["driver_link"]
