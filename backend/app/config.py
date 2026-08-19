import os


DRY_RUN = os.getenv("DRY_RUN", "1") == "1"
NAVCONNECT_ENDPOINT = os.getenv(
    "NAVCONNECT_ENDPOINT",
    "https://navigationconnect.googleapis.com/v1",
)
# Isolated Navigation Connect project. This pilot does not create credentials
# or make live Google requests by default.
PROJECT_ID = os.getenv("PROJECT_ID", "coservices-navconnect")
PROJECT_NUMBER = os.getenv("PROJECT_NUMBER", "461566048811")
ANDROID_APP_ID = os.getenv("ANDROID_APP_ID", "ee.coservices.drivertracking")
SERVICE_ACCOUNT = os.getenv(
    "SERVICE_ACCOUNT",
    "navigation-connect-pilot@coservices-navconnect.iam.gserviceaccount.com",
)
NAVCONNECT_PROJECT_ID = os.getenv("NAVCONNECT_PROJECT_ID", PROJECT_ID)
# Topic name is NOT confirmed. Set these after the first real CreateTrip call.
NAVCONNECT_PUBSUB_TOPIC = os.getenv(
    "NAVCONNECT_PUBSUB_TOPIC",
    "projects/coservices-navconnect/topics/navconnect-trip-updates",
)
NAVCONNECT_SUBSCRIPTION = os.getenv(
    "NAVCONNECT_SUBSCRIPTION",
    "projects/coservices-navconnect/subscriptions/navconnect-trip-updates-sub",
)
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "http://localhost:8000")
MAPS_API_KEY = os.getenv("MAPS_API_KEY", "")
