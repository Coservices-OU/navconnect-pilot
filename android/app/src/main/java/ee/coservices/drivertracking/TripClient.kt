package ee.coservices.drivertracking

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

data class TripResponse(
    val tripId: String,
    val driverLink: String,
    val trackingUrl: String
) {
    companion object {
        fun fromJson(json: String): TripResponse {
            return TripResponse(
                tripId = requiredString(json, "trip_id"),
                driverLink = requiredString(json, "driver_link"),
                trackingUrl = requiredString(json, "tracking_url")
            )
        }

        private fun requiredString(json: String, key: String): String {
            val match = Regex("\\\"$key\\\"\\s*:\\s*\\\"((?:\\\\.|[^\\\"\\\\])*)\\\"").find(json)
                ?: throw IllegalArgumentException("Missing JSON field: $key")
            return match.groupValues[1]
                .replace("\\\\\\\"", "\\\"")
                .replace("\\\\\\\\", "\\\\")
        }
    }
}

class TripClient(private val backendUrl: String = Config.BACKEND_URL) {
    fun createTrip(destinationLat: Double, destinationLng: Double): TripResponse {
        val connection = (URL(backendUrl.trimEnd('/') + "/trips").openConnection() as HttpURLConnection)
        try {
            val requestBody = "{\"destination_lat\":$destinationLat,\"destination_lng\":$destinationLng}"

            connection.requestMethod = "POST"
            connection.connectTimeout = 10_000
            connection.readTimeout = 10_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(requestBody.toByteArray(Charsets.UTF_8)) }

            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val responseText = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (status != HttpURLConnection.HTTP_OK) {
                throw IOException("HTTP $status${if (responseText.isNotBlank()) ": $responseText" else ""}")
            }
            return TripResponse.fromJson(responseText)
        } finally {
            connection.disconnect()
        }
    }
}
