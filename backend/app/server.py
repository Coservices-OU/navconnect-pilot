import logging
from pathlib import Path
from typing import Any
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import config, navconnect
from . import receiver as pubsub_receiver
from .store import store

log = logging.getLogger(__name__)

app = FastAPI(title="Navigation Connect pilot")
_pubsub_subscriber_future = None


@app.on_event("startup")
async def _start_pubsub_listener() -> None:
    """Start the Navigation Connect Pub/Sub subscriber IN-PROCESS, sharing
    this same module's `store` singleton.

    FOUND 2026-09-01 (WB-P000051-T2762, real E2E test): app/receiver.py's
    run() was written to be launched as a fully separate process/script.
    Since app/store.py's `store` is a plain in-process dict-backed
    singleton (no external DB/Redis for this pilot), a separate receiver
    process would hold its OWN empty store -- it would never see trips
    created via this server's POST /trips, and any update it applied would
    be invisible to /operator and /trips here. Fix: run the same
    subscriber callback inside this process instead. pubsub_v1's
    .subscribe() manages its own background threads and returns
    immediately (non-blocking) -- we deliberately do NOT call
    future.result() (that blocks forever and is only correct for a
    standalone script's main thread).
    """
    global _pubsub_subscriber_future
    if config.DRY_RUN:
        log.info("DRY_RUN active -- not starting the Pub/Sub listener.")
        return
    try:
        from google.cloud import pubsub_v1

        creds = navconnect.get_gcloud_cli_credentials()
        client = pubsub_v1.SubscriberClient(credentials=creds)
        _pubsub_subscriber_future = client.subscribe(
            config.NAVCONNECT_SUBSCRIPTION, callback=pubsub_receiver.callback
        )
        log.warning(
            "Pub/Sub listener started in-process on %s",
            config.NAVCONNECT_SUBSCRIPTION,
        )
    except Exception as exc:
        log.error("Failed to start Pub/Sub listener: %s", exc)
TEMPLATE = Path(__file__).parent / "templates" / "tracking.html"
START_TEMPLATE = Path(__file__).parent / "templates" / "start_trip.html"
OPERATOR_TEMPLATE = Path(__file__).parent / "templates" / "operator.html"


class TripRequest(BaseModel):
    destination_lat: float
    destination_lng: float
    trip_id: str | None = None
    vehicle_label: str | None = None
    customer_ref: str | None = None


@app.post("/trips")
async def create_trip(request: TripRequest) -> dict[str, Any]:
    if request.trip_id is None:
        trip_id = str(uuid.uuid4())
    else:
        try:
            uuid.UUID(request.trip_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise HTTPException(
                400, "trip_id must be a valid RFC-4122 UUID"
            ) from exc
        trip_id = request.trip_id
    result = navconnect.create_trip(
        trip_id,
        android_app_id=config.ANDROID_APP_ID,
        destination_lat=request.destination_lat,
        destination_lng=request.destination_lng,
    )
    trip = store.create(
        result["trip_id"],
        request.vehicle_label,
        request.customer_ref,
    )
    return {
        "trip_id": trip.trip_id,
        "driver_link": result.get("driver_link"),
        "driver_link_fallback": result.get("driver_link_fallback"),
        "driver_link_waze": result.get("driver_link_waze"),
        "tracking_url": (
            f"{config.TRACKING_BASE_URL.rstrip('/')}/t/{trip.share_token}"
        ),
    }


@app.get("/trips")
async def list_trips() -> dict[str, Any]:
    """Operator-facing view: what is happening right now, across all trips
    tracked in this process's memory (pilot has no persistent DB yet).
    Includes the internal tracking share_token/URL since this endpoint is
    for Coservices operators only, not customers -- do not expose this
    route outside the Tailscale-bound pilot host."""
    trips = []
    for trip in store.list_all():
        trips.append({
            "trip_id": trip.trip_id,
            "vehicle_label": trip.vehicle_label,
            "customer_ref": trip.customer_ref,
            "created_at": trip.created_at.isoformat(),
            "expires_at": trip.expires_at.isoformat(),
            "update_count": trip.update_count,
            "tracking_url": (
                f"{config.TRACKING_BASE_URL.rstrip('/')}/t/{trip.share_token}"
            ),
            "latest": trip.latest.to_public_dict() if trip.latest else None,
        })
    trips.sort(key=lambda item: item["created_at"], reverse=True)
    return {"count": len(trips), "trips": trips}


@app.get("/operator", response_class=HTMLResponse)
async def operator_page() -> str:
    """Read-only live view of active trips for Coservices operators, polling
    GET /trips every 5s. Deliberately NOT wired into dash.coservices.ee yet --
    that app is the shared France Workboard dashboard, actively edited by other
    tasks (T2700/T2728/T2729); merging there needs coordination first. This is
    a standalone, single-writer page inside navconnect-pilot itself."""
    return OPERATOR_TEMPLATE.read_text(encoding="utf-8")


@app.get("/start", response_class=HTMLResponse)
async def start_trip_page() -> str:
    """No-install driver entry point: dispatch sends this URL (with
    ?lat=..&lng=.. query params) per job via SMS/WhatsApp/CRM. The page
    itself calls POST /trips and redirects the phone browser straight to
    the returned driver_link — no APK, no Play Protect warning, works on
    iOS and Android identically. See WB-P000051 decision notes.
    """
    return START_TEMPLATE.read_text(encoding="utf-8")


@app.get("/t/{share_token}", response_class=HTMLResponse)
async def tracking_page(share_token: str) -> str:
    if store.by_token(share_token) is None:
        raise HTTPException(404, "Tracking link not found")
    return (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__SHARE_TOKEN__", share_token)
        .replace("__MAPS_API_KEY__", config.MAPS_API_KEY)
    )


@app.get("/api/t/{share_token}")
async def tracking_api(share_token: str) -> dict[str, Any]:
    trip = store.by_token(share_token)
    if trip is None:
        raise HTTPException(404, "Tracking link not found")
    if trip.latest is None:
        return {"state": None, "waiting": True}
    return trip.latest.to_public_dict()


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, **store.stats(), "dry_run": config.DRY_RUN}
