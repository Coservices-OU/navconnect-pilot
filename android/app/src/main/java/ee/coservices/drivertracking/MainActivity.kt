package ee.coservices.drivertracking

import android.app.Activity
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
                runOnUiThread { openDriverLink(response.driverLink) }
            } catch (error: Exception) {
                runOnUiThread {
                    Toast.makeText(this, "Trip failed: ${error.message ?: "unknown error"}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun openDriverLink(driverLink: String) {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(driverLink)).apply {
            putExtra(Intent.EXTRA_REFERRER_NAME, "android-app://$packageName")
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
