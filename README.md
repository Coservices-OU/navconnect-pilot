# Navigation Connect pilot (WB-P000051)

Internal Coservices pilot for tracking a driver's live position by piggy-backing on
Google Maps / Waze through Google's **Navigation Connect API**, instead of building
our own in-app navigation. The driver keeps using the navigation app they already
know; we get location/ETA telemetry back for a customer-facing tracking page.

This repo is the pilot proof-of-concept built and verified entirely on Coservices'
own infrastructure (GCP project `coservices-navconnect`, France server) before any
client (Wagner) involvement. Everything below is either taken from Google's official
docs or was confirmed by a real, logged API call from this project — nothing here is
guessed.

## Architecture

```
Android wrapper app  --POST /trips-->  FastAPI backend  --CreateTrip-->  Navigation Connect API
      |                                      |                                  |
      | opens deep link with action_token    |                                  v
      v                                      |                          authToken + trip state
 Google Maps / Waze                          |                                  |
      |                                      v                                  |
      +----- driver navigates ------>  Pub/Sub topic  <------------ Google publishes updates
                                             |
                                             v
                                    customer tracking page (/t/<token>)
```

- `backend/` - FastAPI service. `POST /trips` creates a trip via Navigation Connect
  and returns a driver deep link + a customer tracking URL. `GET /t/{token}` serves a
  minimal German tracking page; `GET /api/t/{token}` is the JSON it polls.
- `android/` - Minimal Android wrapper (Kotlin, no navigation UI of our own). Calls
  the backend, then opens the returned link in Google Maps (fallback: any handler).

## Real facts confirmed during this pilot (not from docs alone)

1. **CreateTrip real response shape** (confirmed 2026-08-18, HTTP 200, task T2393):
   the response does **not** contain a `driverLink` field. It returns:
   ```json
   {
     "name": "projects/<project_number>/trips/<trip_id>",
     "authToken": {"token": "<jwt>", "expireTime": "..."},
     "state": "NEW",
     "execution": {"traveledDistanceMeters": 0, "stopAddedInRoute": false},
     "createTime": "...", "updateTime": "...", "config": {"enablePubsub": true}
   }
   ```
   We build the driver deep link ourselves from `authToken.token` + destination
   (see `backend/app/navconnect.py::build_driver_link`).

2. **`iosAppId` is not mandatory.** A `CreateTrip` call with only `androidAppId` set
   (no `iosAppId`) was accepted with HTTP 200. Earlier internal notes assumed both
   were required per the field docs; that assumption was wrong in practice.

3. **Deep link formats** (from Google's official docs, `launch-navigation-app`):
   - Google Maps: `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>&dir_action=navigate&action_token=<token>`
   - Waze: `https://waze.com/ul?ll=<lat>,<lng>&navigate=yes&external_trip_token=<token>`
   - Android `Intent` must carry `EXTRA_REFERRER_NAME = "android-app://" + packageName`
     or Google Maps/Waze silently refuse the trip token (confirmed the hard way in an
     earlier session, T2046). This repo's Android wrapper only builds the Maps link
     today; Waze support is a small, known follow-up (see Open items below).

4. **Trip state machine** (from Google's docs): `NEW` -> `ENROUTE` -> one of
   `ARRIVED` / `SUSPENDED` / `FAILED` / `CLIENT_ERROR`. `NEW` is the normal state
   right after `CreateTrip`, before the driver has opened navigation - not an error.

5. **`targetSdk 34` blocks plain HTTP by default.** Discovered on a real Huawei P20
   Pro self-test (T1938): the backend was reachable but the app refused the request
   with `Cleartext HTTP traffic to <ip> not permitted`. Fixed with a
   `network_security_config.xml` that allow-lists cleartext for the pilot's specific
   test IP only (see `android/app/src/main/res/xml/network_security_config.xml`).
   A production deployment should use HTTPS and drop this exception entirely.

6. **Pub/Sub IAM is still an open question.** Our topic/subscription
   (`navconnect-trip-updates` / `-sub`) exist with a 24h retention, but the topic's
   IAM policy is still empty - no publish grant to any Google service agent was
   auto-added by `CreateTrip`. We have not yet seen a real Pub/Sub message arrive.
   Getting one likely requires an actual device to open the returned link and start
   real navigation (state -> `ENROUTE`), which is a bigger step than the single
   `CreateTrip` call this pilot has made so far.

7. **Real per-trip cost is not yet known.** `CreateTrip` succeeded, but Google
   Cloud billing data has latency (often hours); the actual line-item cost for this
   one call had not appeared in billing as of this pilot. Budget is capped at
   GBP 10/month on the isolated `coservices-navconnect` project specifically so a
   mistake here cannot become expensive.

8. **App verification is per-GCP-project**, not portable. This pilot verified
   `ee.coservices.drivertracking` on `coservices-navconnect` (~1-3 business days for
   Google to approve, free). Moving the same app to a client's own GCP project will
   require repeating verification there.

## Safety model this pilot follows

- `DRY_RUN=1` is the default (see `backend/app/config.py`). No real Google API call
  happens unless `DRY_RUN=0` is explicitly set, and that has only ever been done
  once, deliberately, with a human's explicit go-ahead for that specific call.
- The GCP project (`coservices-navconnect`) is isolated from all client/production
  projects, with its own budget cap and its own OAuth/app verification, specifically
  so pilot mistakes cannot affect a client's billing or consent screen.
- Nothing here has touched any client infrastructure. This is 100% internal
  Coservices testing.

## Open items before this can be shown to a client

- Confirm real per-trip pricing once it appears in billing.
- Resolve Pub/Sub telemetry: figure out what IAM grant (if any) is required, or
  whether telemetry only starts once a device is actively navigating.
- Add Waze deep-link support in the Android wrapper (currently Maps-only).
- Move the backend behind HTTPS and drop the cleartext exception before any
  external device (i.e. not our own test phone) uses it.
- Repeat app verification under the client's own GCP project when the time comes.

## Layout

```
backend/   FastAPI service + tests (pytest, 19 tests, all offline/mocked)
android/   Minimal Kotlin wrapper app (Gradle, targetSdk 34, minSdk 26)
```

See `backend/NOTES.md` for the fuller day-by-day pilot log.
