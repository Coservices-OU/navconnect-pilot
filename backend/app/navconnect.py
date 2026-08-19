"""Navigation Connect API boundary based on the official documented schema.

Google chooses the Pub/Sub topic. Topic provisioning mechanics are not
described in the docs and must be checked during the first real request.

Confirmed by a real Navigation Connect API CreateTrip call on 2026-08-18
(WB-P000051-T2393, HTTP 200): the response does NOT contain a driverLink
field. It returns {"name", "authToken": {"token", "expireTime"}, "state",
"execution", "createTime", "updateTime", "config"}. The deep link must be
built by us using the confirmed format from Google's official docs
(developers.google.com/maps/documentation/navigation/connect/launch-navigation-app):

  https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>
    &dir_action=navigate&action_token=<authToken.token>

Also confirmed: androidAppId alone (without iosAppId) is accepted with
HTTP 200 - iosAppId is NOT strictly mandatory when there is no iOS app.
"""

import logging
from typing import Any
from urllib.parse import quote
import uuid

from . import config

log = logging.getLogger(__name__)


class NavConnectError(RuntimeError):
    pass


def build_driver_link(
    destination_lat: float | None,
    destination_lng: float | None,
    action_token: str | None,
) -> str | None:
    if destination_lat is None or destination_lng is None or action_token is None:
        return None
    return (
        "https://www.google.com/maps/dir/?api=1&destination="
        f"{quote(str(destination_lat))},{quote(str(destination_lng))}"
        f"&dir_action=navigate&action_token={quote(action_token)}"
    )


def create_trip(
    trip_id: str,
    android_app_id: str | None = None,
    ios_app_id: str | None = None,
    enable_pubsub: bool = True,
    pubsub_field_mask: str | None = None,
    destination_lat: float | None = None,
    destination_lng: float | None = None,
) -> dict[str, Any]:
    try:
        uuid.UUID(trip_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise NavConnectError(
            "trip_id must be a valid RFC-4122 UUID"
        ) from exc

    body: dict[str, Any] = {"config": {"enablePubsub": enable_pubsub}}
    if android_app_id is not None:
        body["androidAppId"] = android_app_id
    if ios_app_id is not None:
        body["iosAppId"] = ios_app_id
    if pubsub_field_mask is not None:
        # This is an exclusion mask for heavy fields, not an include list.
        body["config"]["pubsubFieldMask"] = pubsub_field_mask
    if config.DRY_RUN:
        log.warning("DRY_RUN Navigation Connect request body: %s", body)
        return {
            "trip_id": trip_id,
            "driver_link": build_driver_link(
                destination_lat, destination_lng, "DRY_RUN_FAKE_TOKEN"
            ),
            "dry_run": True,
            "request_body_preview": body,
        }
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        response = AuthorizedSession(credentials).post(
            (
                config.NAVCONNECT_ENDPOINT.rstrip("/")
                + f"/projects/{config.NAVCONNECT_PROJECT_ID}/trips"
            ),
            json=body,
            params={"tripId": trip_id},
            headers={
                "X-Goog-User-Project": project_id or config.NAVCONNECT_PROJECT_ID
            },
        )
    except Exception as exc:
        raise NavConnectError(str(exc)) from exc
    if not response.ok:
        raise NavConnectError(response.text)
    data = response.json()
    trip_id = (
        data.get("tripId")
        or data.get("trip_id")
        or data.get("name", "").rstrip("/").rsplit("/", 1)[-1]
    )
    action_token = (data.get("authToken") or {}).get("token")
    driver_link = data.get("driverLink") or data.get("driver_link") or build_driver_link(
        destination_lat, destination_lng, action_token
    )
    return {
        "trip_id": trip_id,
        "driver_link": driver_link,
        "dry_run": False,
        "response": data,
    }
