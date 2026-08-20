import asyncio
import uuid

import httpx

from app.server import app
from app.store import store


def test_trip_and_tracking_api(monkeypatch):
    monkeypatch.setattr(
        "app.server.navconnect.create_trip",
        lambda *args, **kwargs: {
            "trip_id": args[0],
            "driver_link": "x",
            "dry_run": True,
        },
    )
    store._trips.clear()

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/trips",
                json={"destination_lat": 1, "destination_lng": 2},
            )
            assert response.status_code == 200
            token = response.json()["tracking_url"].rsplit("/", 1)[-1]
            tracking_response = await client.get(f"/api/t/{token}")
            missing_response = await client.get("/api/t/bad-token")

            assert tracking_response.json() == {"state": None, "waiting": True}
            assert missing_response.status_code == 404

    asyncio.run(exercise())


def test_post_trip_generates_uuid(monkeypatch):
    monkeypatch.setattr(
        "app.server.navconnect.create_trip",
        lambda trip_id, *args, **kwargs: {"trip_id": trip_id, "driver_link": "x", "dry_run": True},
    )
    store._trips.clear()

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/trips", json={"destination_lat": 1, "destination_lng": 2}
            )
            assert response.status_code == 200
            uuid.UUID(response.json()["trip_id"])

    asyncio.run(exercise())


def test_post_trip_rejects_invalid_trip_id():
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/trips",
                json={
                    "destination_lat": 1,
                    "destination_lng": 2,
                    "trip_id": "nesamone",
                },
            )
            assert response.status_code == 400
            assert "RFC-4122 UUID" in response.json()["detail"]

    asyncio.run(exercise())


def test_start_page_serves_html():
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/start")
            assert response.status_code == 200
            assert "fetch" in response.text
            assert "/trips" in response.text

    asyncio.run(exercise())


def test_list_trips_operator_endpoint():
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            create_resp = await client.post(
                "/trips",
                json={
                    "destination_lat": 54.68,
                    "destination_lng": 25.28,
                    "vehicle_label": "VAN-1",
                    "customer_ref": "TEST-REF",
                },
            )
            assert create_resp.status_code == 200
            created_trip_id = create_resp.json()["trip_id"]

            list_resp = await client.get("/trips")
            assert list_resp.status_code == 200
            body = list_resp.json()
            assert body["count"] >= 1
            match = next(
                item for item in body["trips"] if item["trip_id"] == created_trip_id
            )
            assert match["vehicle_label"] == "VAN-1"
            assert match["customer_ref"] == "TEST-REF"
            assert "tracking_url" in match

    asyncio.run(exercise())
