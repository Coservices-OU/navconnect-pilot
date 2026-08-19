package ee.coservices.drivertracking

import kotlin.test.Test
import kotlin.test.assertEquals

class TripClientTest {
    @Test
    fun parsesExampleJsonWithoutNetworkCall() {
        val json = """{
            "trip_id": "trip-123",
            "driver_link": "https://maps.google.com/?q=59.437,24.754",
            "tracking_url": "https://example.invalid/tracking/trip-123"
        }"""

        val response = TripResponse.fromJson(json)

        assertEquals("trip-123", response.tripId)
        assertEquals("https://maps.google.com/?q=59.437,24.754", response.driverLink)
        assertEquals("https://example.invalid/tracking/trip-123", response.trackingUrl)
    }
}
