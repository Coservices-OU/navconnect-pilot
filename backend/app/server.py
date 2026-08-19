from pathlib import Path
from typing import Any
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import config, navconnect
from .store import store

app = FastAPI(title="Navigation Connect pilot")
TEMPLATE = Path(__file__).parent / "templates" / "tracking.html"


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
        "tracking_url": (
            f"{config.TRACKING_BASE_URL.rstrip('/')}/t/{trip.share_token}"
        ),
    }


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
