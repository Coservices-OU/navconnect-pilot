package ee.coservices.drivertracking

import android.app.Activity
import android.app.PendingIntent
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
        }
        layout.addView(TextView(this).apply { text = "Destination latitude" })
        val latitude = EditText(this).apply { setText("59.4370") }
        layout.addView(latitude)
        layout.addView(TextView(this).apply { text = "Destination longitude" })
        val longitude = EditText(this).apply { setText("24.7536") }
        layout.addView(longitude)
        layout.addView(Button(this).apply {
            text = "Start Trip"
            setOnClickListener {
                startTrip(latitude.text.toString(), longitude.text.toString())
            }
        })
        setContentView(layout)
    }

    private fun startTrip(latitudeText: String, longitudeText: String) {
        val latitude = latitudeText.toDoubleOrNull()
        val longitude = longitudeText.toDoubleOrNull()
        if (latitude == null || longitude == null) {
            Toast.makeText(this, "Enter valid destination coordinates", Toast.LENGTH_LONG).show()
            return
        }

        executor.execute {
            try {
                val response = TripClient().createTrip(latitude, longitude)
                // FIX 2026-09-11 (WB-P000051-T2762, "codex" repair): use the bare,
                // un-wrapped driverLinkFallback URL here, not the pre-composed
                // intent://...#Intent;...;end driverLink string. openDriverLink()
                // below builds its own single native Intent and attaches the real
                // Intent.EXTRA_REFERRER_NAME extra itself -- that is the mandatory
                // app-id attribution per Google's Navigation Connect docs. Passing
                // the already-encoded driverLink here caused a double-wrap (Uri.parse()
                // does not decode an intent:// URI's #Intent;...;end fragment into
                // real extras), which is the likely cause of every prior real-device
                // test staying stuck in NEW with no consent dialog.
                runOnUiThread { openDriverLink(response.driverLinkFallback) }
            } catch (error: Exception) {
                runOnUiThread {
                    Toast.makeText(this, "Trip failed: ${error.message ?: "unknown error"}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun openDriverLink(driverLink: String) {
        // FIX 2026-09-14 (WB-P000051-T2762, independent-review repair): Google's
        // own sample code for launching Navigation Connect on Android also
        // attaches a PendingIntent under the "pendingIntent" extra key, used by
        // Maps/Waze to power the branded "return to app" button after the trip.
        // It was missing here (docs confirm it is required, not optional) --
        // added per independent doc-verification review.
        val returnIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val returnPendingIntent = PendingIntent.getActivity(
            this,
            0,
            returnIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(driverLink)).apply {
            putExtra(Intent.EXTRA_REFERRER_NAME, "android-app://$packageName")
            putExtra("pendingIntent", returnPendingIntent)
            setPackage("com.google.android.apps.maps")
        }
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            intent.setPackage(null)
            try {
                startActivity(intent)
            } catch (_: ActivityNotFoundException) {
                Toast.makeText(this, "No navigation app can open this link", Toast.LENGTH_LONG).show()
            }
        }
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }
}
