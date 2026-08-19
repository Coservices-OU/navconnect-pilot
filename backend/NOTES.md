# Navigation Connect pilot notes

Canonical France Workboard task: **WB-P000051-T2116**.

## Isolated GCP project

Configuration now targets `coservices-navconnect` (project number
`461566048811`) with service account
`navigation-connect-pilot@coservices-navconnect.iam.gserviceaccount.com`.
The project already has `roles/navigationconnect.admin` and
`roles/pubsub.subscriber`; the Navigation Connect, Pub/Sub, and Billing Budgets
APIs are enabled. Its budget is GBP 10/month, scoped only to this project, with
a GBP 0 baseline because it is new.

The separate project is necessary because `coservices-marketingin` already uses
its single OAuth branding for "Marketing IN Google Ads MCP" (n8n OAuth + Ads
MCP, External, In production, OAuth user cap 1/100 that cannot be reset).
Verifying Navigation Connect there could change the consent screen of the live
production integration. This pilot gets separate branding, Testing status, and
isolated cost measurement.

Implemented the DRY_RUN-first FastAPI pilot, tolerant parser, in-memory store,
isolated API boundary, Pub/Sub receiver, German tracking page, and offline tests.

## Confirmed from official Navigation Connect documentation

- Pub/Sub updates use `execution.location.point`, `sourceTime`,
  `remainingDuration` as a duration string, and `remainingDistanceMeters`.
- Create-trip is `POST /v1/projects/{PROJECT_ID}/trips?tripId={TRIP_ID}` with
  `androidAppId`, `iosAppId`, and `config.enablePubsub`.
- `config.pubsubFieldMask` excludes heavy fields; it is not an include list.
- The client generates `tripId`. Destination is not part of the create-trip
  body and is kept in the launch URL.

## 2026-08-18 update: app verified, first real CreateTrip call made

- App `ee.coservices.drivertracking` verification for Navigation Connect on
  `coservices-navconnect` is confirmed "Verified" (checked live in Google
  Cloud Console, not from a stale note).
- Pub/Sub topic `navconnect-trip-updates` and subscription
  `navconnect-trip-updates-sub` created with 24h message retention. Their IAM
  policy is still empty (no publish grant added automatically by CreateTrip).
- An unused, unrestricted "Maps Platform API Key" (33 API targets, no app/IP
  restriction) that onboarding had silently created was deleted after
  confirming via grep that nothing in this codebase referenced it (WB-P000051-T2390).
- Android wrapper build toolchain (JDK 17, Android SDK, Gradle 8.9) installed
  on the France server; wrapper builds and passes its unit test
  (WB-P000051-T2391).
- Real self-test on a Huawei P20 Pro over Tailscale (WB-P000051-T1938):
  the backend was unreachable over plain HTTP by default on targetSdk 34
  (`Cleartext HTTP traffic ... not permitted`); fixed with a
  `network_security_config.xml` cleartext allow-list scoped to the pilot's
  single test IP. After the fix, the wrapper successfully opened Google Maps
  with a DRY_RUN trip link.
- **First real (`DRY_RUN=0`) `CreateTrip` call made and confirmed HTTP 200**
  (WB-P000051-T2393), with explicit authorization for this specific call.
  The real response does **not** include a `driverLink` field - only
  `authToken.token`, `state: "NEW"`, `execution`, `createTime`/`updateTime`.
  `backend/app/navconnect.py` was updated to build the Google Maps deep link
  itself from `authToken.token` + destination, per Google's documented
  format (`dir_action=navigate&action_token=...`). Before this fix, a real
  (non-DRY_RUN) trip would have opened Maps with an *untracked* route - a
  latent bug that only real testing surfaced.
- `iosAppId` was **not** required in practice - a call with only
  `androidAppId` set returned HTTP 200.
- Real per-trip billing had not yet appeared in the billing console as of
  this call (Google billing data has latency); cost is still unconfirmed.
- Pub/Sub still shows no published messages and no IAM grant - likely because
  telemetry only starts once a device is actively navigating (state
  `ENROUTE`), which this pilot has deliberately not yet done.

## Not verified / open

- Real per-trip cost (billing latency).
- What IAM principal (if any) needs Pub/Sub publish rights, or whether
  telemetry flows through a different mechanism entirely.
- Waze deep-link support (Android wrapper currently targets Google Maps only).
- Behavior once a trip actually starts navigating (state transitions past `NEW`).
