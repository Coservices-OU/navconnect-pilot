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

    UPDATE 2026-09-01 (WB-P000051-T2762, real E2E test): user reported the
    /start page taking noticeably long to load. Measured it: a plain
    google.auth.default() call on THIS host takes ~12s to fail (it tries
    to reach the GCE metadata server at 169.254.169.254, which times out
    slowly rather than refusing fast, since this France host is not a GCP
    VM -- a fact this docstring already stated but the code didn't act on)
    before falling back to the working `gcloud auth print-access-token`
    path, which alone takes ~0.6s. That's a 12s tax on every single
    request for a path we already know never succeeds here. Fix: try the
    known-working gcloud CLI path FIRST; only fall back to ADC if that
    fails (e.g. if this ever runs on a real GCP VM in future, or the
    gcloud CLI session expires).
    """
    import subprocess

    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        token = result.stdout.strip()
        if token:
            return token, None
        cli_exc = NavConnectError(
            "gcloud auth print-access-token returned an empty token"
        )
    except Exception as exc:
        cli_exc = exc

    try:
        import google.auth
        import google.auth.transport.requests

        credentials, project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token, project_id
    except Exception as adc_exc:
        raise NavConnectError(
            f"gcloud CLI fallback failed ({cli_exc}) and no ADC ({adc_exc})"
        ) from adc_exc


class _GcloudCliCredentials:
    """A minimal, auto-refreshing google-auth Credentials implementation
    backed by the already-authenticated `gcloud` CLI session on this host.

    FOUND 2026-09-01 (WB-P000051-T2762, real E2E test): pubsub_v1's
    SubscriberClient() uses google.auth.default() (ADC) by default, which
    fails on this host with "Your default credentials were not found" --
    the exact same ADC gap _get_access_token() above already works around
    for the REST CreateTrip call via `gcloud auth print-access-token`. A
    plain one-shot token string isn't enough here though: the Pub/Sub
    streaming pull is long-lived and the token expires in ~1h, so this
    wraps the same CLI fallback in a real refreshable Credentials object
    (google-auth calls .refresh() itself whenever .valid is False).
    """

    def __init__(self) -> None:
        self.token: str | None = None
        self.expiry = None

    @property
    def expired(self) -> bool:
        import datetime

        return self.expiry is None or datetime.datetime.utcnow() >= self.expiry

    @property
    def valid(self) -> bool:
        return self.token is not None and not self.expired

    def refresh(self, request) -> None:  # noqa: ARG002 - google-auth API shape
        import datetime
        import subprocess

        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        token = result.stdout.strip()
        if not token:
            raise NavConnectError(
                "gcloud auth print-access-token returned an empty token"
            )
        self.token = token
        self.expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=50)

    def apply(self, headers: dict, token: str | None = None) -> None:  # noqa: ARG002
        headers["authorization"] = f"Bearer {token or self.token}"

    def before_request(self, request, method, url, headers) -> None:  # noqa: ARG002
        if not self.valid:
            self.refresh(request)
        self.apply(headers)


def get_gcloud_cli_credentials() -> "_GcloudCliCredentials":
    """Build Pub/Sub-compatible credentials from the gcloud CLI fallback,
    for use where ADC is broken (see _GcloudCliCredentials docstring)."""
    creds = _GcloudCliCredentials()
    creds.refresh(None)
    return creds


def build_driver_link(
    destination_lat: float | None,
    destination_lng: float | None,
    action_token: str | None,
    android_app_id: str | None = None,
) -> str | None:
    if destination_lat is None or destination_lng is None or action_token is None:
        return None
    # FOUND 2026-09-01 (WB-P000051-T2762, real E2E walking test): Google's
    # own docs (developers.google.com/maps/documentation/navigation/connect/
    # launch-navigation-app) state verbatim: "If the driver navigates in a
    # non-driving mode, Navigation Connect won't return telemetry updates or
    # traffic information." Our link had no travelmode param, so Maps chose
    # a mode itself -- during walking tests it silently produced ZERO
    # telemetry (state stuck at NEW, traveledDistanceMeters: 0) even though
    # real active navigation with live rerouting was happening on-screen.
    # This was the root cause of every "no data" result across all real
    # test trips so far -- not a pipeline/GCP bug. Force driving mode
    # explicitly so this pilot (built for delivery/moving-truck drivers)
    # always gets telemetry.
    query = (
        "api=1&destination="
        f"{quote(str(destination_lat))},{quote(str(destination_lng))}"
        f"&travelmode=driving"
        f"&dir_action=navigate&action_token={quote(action_token)}"
    )
    https_url = f"https://www.google.com/maps/dir/?{query}"
    if not android_app_id:
        return https_url
    referrer = quote(f"android-app://{android_app_id}", safe="")
    fallback = quote(https_url, safe="")
    return (
        "intent://maps.google.com/dir/?" + query +
        "#Intent;scheme=https;package=com.google.android.apps.maps;"
        f"S.android.intent.extra.REFERRER_NAME={referrer};"
        f"S.browser_fallback_url={fallback};end"
    )


def build_waze_link(
    destination_lat: float | None,
    destination_lng: float | None,
    action_token: str | None = None,
    android_app_id: str | None = None,
) -> str | None:
    """Build a Waze deep link per Google's Navigation Connect API docs
    (developers.google.com/maps/documentation/navigation/connect/launch-navigation-app).

    UPDATE 2026-09-01 (WB-P000051-T2762): user reported Google Maps opened
    correctly via the intent:// link, but no app chooser offering other
    installed navigation apps (Waze) appeared -- expected, since the Maps
    intent explicitly pins package=com.google.android.apps.maps, which
    bypasses the Android chooser entirely. Google's own docs confirm Waze
    is a first-class Navigation Connect target with its own universal link
    (https://waze.com/ul) and its own attribution extra
    (EXTRA_REFERRER_NAME), separate from the Maps intent:// link -- there is
    no single generic intent that offers both under one chooser while
    keeping attribution for either. Fix: expose Waze as its own explicit
    link/button next to the Maps one, same pattern as driver_link_fallback.
    A plain https://waze.com/ul link is a real Android App Link (like
    Maps'), so a genuine <a href> tap (no JS redirect) is enough to trigger
    it without needing intent:// syntax.
    """
    if destination_lat is None or destination_lng is None:
        return None
    query = f"ll={quote(str(destination_lat))}%2C{quote(str(destination_lng))}&navigate=yes"
    if action_token:
        query += f"&external_trip_token={quote(action_token)}"
    return f"https://waze.com/ul?{query}"


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
            "driver_link_waze": build_waze_link(
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
    driver_link_waze = build_waze_link(
        destination_lat, destination_lng, action_token
    )
    return {
        "trip_id": trip_id,
        "driver_link": driver_link,
        "driver_link_fallback": driver_link_fallback,
        "driver_link_waze": driver_link_waze,
        "dry_run": False,
        "response": data,
    }
