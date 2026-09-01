import json
import logging

from .models import TripUpdate
from .store import store

log = logging.getLogger(__name__)


def callback(message) -> None:
    try:
        raw = json.loads(message.data)
        # TEMP 2026-09-01 (WB-P000051-T2762): Google's docs only say
        # messages arrive in "a standard message envelope" without
        # documenting its exact shape. Logging the raw payload once so we
        # can fix TripUpdate.from_payload's field paths against the real
        # schema instead of guessing.
        log.warning("RAW Pub/Sub payload: %s", json.dumps(raw)[:4000])
        log.warning("RAW Pub/Sub attributes: %s", dict(message.attributes))
        update = TripUpdate.from_payload(raw)
        if store.apply_update(update) is None:
            log.warning("Received update for unknown trip: %s", update.trip_id)
        message.ack()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        log.error("Bad Pub/Sub JSON: %s", exc)
        message.ack()


def run() -> None:
    from google.cloud import pubsub_v1
    from google.api_core.exceptions import NotFound

    from . import config

    try:
        future = pubsub_v1.SubscriberClient().subscribe(
            config.NAVCONNECT_SUBSCRIPTION,
            callback=callback,
        )
        future.result()
    except NotFound:
        log.error(
            "Pub/Sub subscription does not exist: %s. Check topic provisioning "
            "after the first real CreateTrip call and set "
            "NAVCONNECT_SUBSCRIPTION accordingly.",
            config.NAVCONNECT_SUBSCRIPTION,
        )


if __name__ == "__main__":
    run()
