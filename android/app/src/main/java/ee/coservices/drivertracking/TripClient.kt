package ee.coservices.drivertracking

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

data class TripResponse(
    val tripId: String,
    val driverLink: String,
    // FIX 2026-09-11 (WB-P000051-T2762, "codex" repair per Torben Spitzer /
    // Google Navigation Connect PM confirming application ID is MANDATORY
    // for token auth, and per updated docs at
    // developers.google.com/maps/documentation/navigation/connect/launch-navigation-app#app-id):
    // driverLink is a pre-composed "intent://...#Intent;...;end" URI string
    // with the app-id referrer already baked into the URI fragment via
    // S.android.intent.extra.REFERRER_NAME. MainActivity was wrapping THAT
    // string in a second native Intent + putExtra(EXTRA_REFERRER_NAME, ...),
    // which double-encodes/conflicts with the URI-embedded referrer and is
    // not how Android's real Intent.EXTRA_REFERRER_NAME attribution works
    // (Uri.parse() does not decode "intent://...#Intent;...;end" into real
    // Intent extras -- only Intent.parseUri(..., URI_INTENT_SCHEME) does
    // that). driverLinkFallback is the bare, unwrapped HTTPS Maps URL with
    // NO referrer baked in, meant to be opened via a single real native
    // Intent that carries the referrer as an actual EXTRA_REFERRER_NAME.
    val driverLinkFallback: String,
    val trackingUrl: String
) {
    companion object {
        fun fromJson(json: String): TripResponse {
            return TripResponse(
                tripId = requiredString(json, "trip_id"),
                driverLink = requiredString(json, "driver_link"),
                driverLinkFallback = requiredString(json, "driver_link_fallback"),
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
