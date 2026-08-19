import json
import logging

from .models import TripUpdate
from .store import store

log = logging.getLogger(__name__)


def callback(message) -> None:
    try:
        update = TripUpdate.from_payload(json.loads(message.data))
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
