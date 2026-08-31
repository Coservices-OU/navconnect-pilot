"""Navigation Connect API boundary based on the official documented schema.

Google chooses the Pub/Sub topic. Topic provisioning mechanics are not
described in the docs and must be checked during the first real request.

CORRECTION 2026-08-20 (WB-P000051-T2767): a previous version of this
docstring claimed a real Navigation Connect API CreateTrip call succeeded on
2026-08-18 (WB-P000051-T2393, HTTP 200). That claim is NOT corroborated:
France Workboard still shows T2393 as status "queued" (never closed with
evidence), and the navconnect-trip-updates Pub/Sub topic IAM policy is
empty -- if a real CreateTrip with enablePubsub=true had ever succeeded,
Google's Navigation Connect service agent would normally have an
auto-granted publish binding there. Real ADC/auth was also confirmed broken
on this host as of 2026-08-20 (see WB-P000051-T2762 evidence). Treat the
response-shape claim below as UNVERIFIED until a real call actually
succeeds and is checked against real evidence.

Unverified claim (kept for reference, not fact): the response does NOT
contain a driverLink field, and returns {"name", "authToken": {"token",
"expireTime"}, "state", "execution", "createTime", "updateTime", "config"}
instead. If true, the deep link must be built by us using the format from
Google's official docs
(developers.google.com/maps/documentation/navigation/connect/launch-navigation-app):

  https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>
    &dir_action=navigate&action_token=<authToken.token>

Also unverified: androidAppId alone (without iosAppId) is accepted with
HTTP 200 - iosAppId claimed to not be strictly mandatory when there is no
iOS app.

UPDATE 2026-08-31 (WB-P000051-T2762, evidence 3596/3600): confirmed in GCP
Console that app "ee.coservices.drivertracking" IS Verified for Navigation
Connect (Keys and credentials > Apps submitted to Navigation Connect API).
So app verification was NOT the blocker. The actual gap: the official docs
(launch-navigation-app) only document launching via a native Android
Intent carrying Intent.EXTRA_REFERRER_NAME="android-app://<packageName>"
plus intent.setPackage("com.google.android.apps.maps") -- our plain
https://www.google.com/maps/dir/... link never carried that referrer extra,
so Maps silently treated the session as unattributed and failed with a
generic "can't connect, check internet" error (identical for DRY_RUN fake
and real tokens -- not a token validity issue). build_driver_link() now
emits an intent:// URI so a plain <a href> tap on Android still carries the
extra, with S.browser_fallback_url degrading to the old https link
everywhere else.

UPDATE 2026-08-31 (later, same task): real phone test showed the intent://
link does *nothing* when tapped (no app switch, no error) -- some mobile
browsers/in-app webviews silently no-op on intent:// instead of following
it, so Chrome's own S.browser_fallback_url (Chrome-only behaviour) isn't a
reliable enough safety net. create_trip() now also returns a separate
driver_link_fallback (the plain https link) so the frontend can implement
its own browser-agnostic fallback (see start_trip.html).
"""

import logging
from typing import Any
from urllib.parse import quote
import uuid

from . import config

log = logging.getLogger(__name__)


class NavConnectError(RuntimeError):
    pass


def _get_access_token() -> tuple[str, str | None]:
    """Get a real OAuth access token for the CreateTrip call.

    Tries Application Default Credentials first (the normal path on a real
    GCP VM). This France host is NOT a GCP VM, so ADC is usually absent --
    in that case we fall back to the already-authenticated `gcloud` CLI
    session on this host (see WB-P000051-T2767) and ask it for a short-lived
    access token via `gcloud auth print-access-token`. The token is used
    in-process only and is never logged or persisted.
    """
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token, project_id
    except Exception as adc_exc:
        import subprocess

        try:
            result = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except Exception as cli_exc:
            raise NavConnectError(
                f"No ADC ({adc_exc}) and gcloud CLI fallback failed ({cli_exc})"
            ) from cli_exc
        token = result.stdout.strip()
        if not token:
            raise NavConnectError(
                "gcloud auth print-access-token returned an empty token"
            )
        return token, None


def build_driver_link(
    destination_lat: float | None,
    destination_lng: float | None,
    action_token: str | None,
    android_app_id: str | None = None,
) -> str | None:
    if destination_lat is None or destination_lng is None or action_token is None:
        return None
    query = (
        "api=1&destination="
        f"{quote(str(destination_lat))},{quote(str(destination_lng))}"
        f"&dir_action=navigate&action_token={quote(action_token)}"
    )
    https_url = f"https://www.google.com/maps/dir/?{query}"
    if not android_app_id:
        return https_url
    # See module docstring "UPDATE 2026-08-31": a plain https link does not
    # carry Intent.EXTRA_REFERRER_NAME, which the docs say is required to
    # attribute the session to our VERIFIED app. Use Android's intent://
    # URI scheme so a normal <a href> tap still forces the real Maps app
    # (package=) and carries the referrer extra. Falls back automatically
    # to the https URL (S.browser_fallback_url) on desktop/iOS/no Maps app.
    referrer = quote(f"android-app://{android_app_id}", safe="")
    fallback = quote(https_url, safe="")
    return (
        "intent://maps.google.com/dir/?" + query +
        "#Intent;scheme=https;package=com.google.android.apps.maps;"
        f"S.android.intent.extra.REFERRER_NAME={referrer};"
        f"S.browser_fallback_url={fallback};end"
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

    # Confirmed by a real Navigation Connect API response on 2026-08-11:
    # CreateTrip rejects non-RFC-4122 trip IDs with HTTP 400. This is confirmed
    # by the real API response, not a guess.
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
                destination_lat, destination_lng, "DRY_RUN_FAKE_TOKEN", android_app_id
            ),
            "driver_link_fallback": build_driver_link(
                destination_lat, destination_lng, "DRY_RUN_FAKE_TOKEN"
            ),
            "dry_run": True,
            "request_body_preview": body,
        }
    try:
        access_token, quota_project = _get_access_token()
    except Exception as exc:
        raise NavConnectError(str(exc)) from exc
    try:
        import requests

        response = requests.post(
            (
                config.NAVCONNECT_ENDPOINT.rstrip("/")
                + f"/projects/{config.NAVCONNECT_PROJECT_ID}/trips"
            ),
            json=body,
            params={"tripId": trip_id},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Goog-User-Project": quota_project or config.NAVCONNECT_PROJECT_ID,
            },
            timeout=30,
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
        destination_lat, destination_lng, action_token, android_app_id
    )
    driver_link_fallback = build_driver_link(
        destination_lat, destination_lng, action_token
    )
    return {
        "trip_id": trip_id,
        "driver_link": driver_link,
        "driver_link_fallback": driver_link_fallback,
        "dry_run": False,
        "response": data,
    }
