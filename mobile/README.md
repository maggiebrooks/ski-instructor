# Ski Recorder (Expo / React Native)

A standalone iOS/Android session recorder for the ski-ai project. It captures
four sensor streams, packages them into a SensorLogger-compatible ZIP, and
uploads to the existing FastAPI backend at `POST /api/upload-session`.

The web app is unchanged; this app is **only** the record → upload client.
Processed results are shown inside this app on the Results screen (and are
also available in the web frontend at the same URL).

## Sensors recorded

| Sensor          | Source             | Rate    | CSV file            |
|-----------------|--------------------|---------|---------------------|
| Accelerometer   | `expo-sensors`     | 100 Hz  | `Accelerometer.csv` |
| Gyroscope       | `expo-sensors`     | 100 Hz  | `Gyroscope.csv`     |
| GPS / Location  | `expo-location` (`Accuracy.BestForNavigation`, `watchPositionAsync`) | 1 Hz | `Location.csv` |
| Barometer       | `expo-sensors`     | 1 Hz    | `Barometer.csv`     |

All four CSVs sit at the **top level** of the ZIP (no subdirectory).

`time` is **nanoseconds since the Unix epoch** (`Date.now() * 1e6`) and
`seconds_elapsed` is `(time - sessionStartTime) / 1e9` where
`sessionStartTime` is captured **once** when the user taps **Start
Recording**, so all four sensors share a single zero.

The Django / FastAPI pipeline only **requires** `Accelerometer.csv` and
`Gyroscope.csv`. `Location.csv` and `Barometer.csv` are bonus data the
pipeline uses if present (the `relativeAltitude` column in `Barometer.csv`
is what `segment_runs()` keys off to detect skiing vs. chairlift).

### CSV column order

```
Accelerometer.csv  time,seconds_elapsed,x,y,z
Gyroscope.csv      time,seconds_elapsed,x,y,z
Location.csv       time,seconds_elapsed,latitude,longitude,altitude,speed,
                   bearing,horizontalAccuracy,verticalAccuracy,
                   speedAccuracy,bearingAccuracy
Barometer.csv      time,seconds_elapsed,relativeAltitude,pressure
```

Speed is in **m/s**, bearing in **degrees (0–360)**, accuracy fields in
**metres**, pressure in **hPa (millibars)**, and `relativeAltitude` in
**metres** relative to the **first barometer reading of the session**.
Any unavailable field is written as `0` (e.g. Android does not expose
`speedAccuracy` or `bearingAccuracy` via `expo-location`).

## Install

```bash
cd mobile
npm install
# Recommended after install: pin Expo-managed SDK packages to the matching
# versions for the installed Expo SDK.
npx expo install --check
```

You need **Node 20+** and the **Expo CLI** (bundled, invoked via `npx expo`).
For iOS native builds you also need **Xcode 16+** (and the iOS simulator).

## Run

### On a physical iPhone via Expo Go (easiest, free)

```bash
npx expo start
```

Open the Expo Go app on your phone and scan the QR code printed in the terminal
(or shown in the dev page that opens in your browser).

> Expo Go is free for development. Publishing to the App Store later requires a
> paid **Apple Developer account ($99/year)**; iCloud / TestFlight share also
> requires that account. You do not need it for everyday development.

> If your phone can't reach the Metro bundler, make sure the phone and the
> Mac are on the **same Wi-Fi network**. If you're on a corporate / guest
> network that blocks peer connections, run `npx expo start --tunnel` to use
> Expo's relay.

### On the iOS simulator

```bash
npx expo run:ios
```

This requires Xcode and creates a native dev client. The first build is slow
(several minutes); subsequent runs are fast.

### On the Android emulator

```bash
npx expo run:android
```

## Configure the backend URL

Both the upload endpoint and the "view results" link live in
[`src/config.ts`](./src/config.ts):

```ts
export const API_BASE_URL = 'http://localhost:8000';
export const WEB_APP_URL  = 'http://localhost:5173';
```

| Environment | `API_BASE_URL` | Notes |
|---|---|---|
| iOS Simulator | `http://localhost:8000` | Simulator shares the host network. |
| Physical iPhone (Expo Go) | `http://<mac-LAN-IP>:8000` | `ipconfig getifaddr en0` on the Mac. Phone + Mac must be on the same Wi-Fi. |
| Android emulator | `http://10.0.2.2:8000` | `10.0.2.2` is the host loopback inside the emulator. |
| Production | `https://<your-api>.up.railway.app` | No trailing `/api`. The client appends `/api/upload-session`. |

`WEB_APP_URL` is only used to open the web app from the success / footer link
(via `Linking.openURL`); it does not affect uploads.

## What gets uploaded

When you tap **Stop Recording**, the app:

1. Stops the four sensor listeners (accelerometer, gyroscope, barometer,
   `Location.watchPositionAsync` subscription).
2. Renders each buffer as CSV using a shared `sessionStartTime` (the moment
   you tapped Start) for `seconds_elapsed`, so all four streams line up at
   `t = 0`.
3. Zips up to four CSVs at the top level using `fflate` (in-memory, no temp
   dirs). `Location.csv` and `Barometer.csv` are only included if at least one
   sample of each was captured.
4. Writes the ZIP to `FileSystem.cacheDirectory` and navigates to the upload
   screen, which shows: duration, accel / gyro / GPS / baro counts, and a
   `GPS available: Yes/No` flag.
5. The upload screen POSTs the ZIP as `multipart/form-data` (field name
   `file`) to `${API_BASE_URL}/api/upload-session`.

The "Upload from Files" path on the home screen accepts an existing
SensorLogger ZIP from the OS file picker and uses the same upload endpoint.

## Permissions

The Record screen requests three permissions on mount, **before** the Start
button is shown:

1. **Motion & Fitness** (accelerometer + gyroscope): *required*. If denied,
   recording is blocked and the screen shows a button that opens
   `Settings → Privacy & Security → Motion & Fitness → Ski Recorder`.
2. **Location (When In Use)**: *recommended*. If denied, recording still
   works but a yellow warning explains that turn detection and speed metrics
   will be limited (no GPS track).
3. **Barometer**: no permission prompt exists on iOS or Android; it just
   works on devices that have one (every iPhone since the 6, every modern
   Pixel and most flagship Androids).

The matching iOS usage strings (`NSMotionUsageDescription`,
`NSLocationWhenInUseUsageDescription`) are declared in
[`app.json`](./app.json).

## Project layout

```
mobile/
├── App.tsx                     Tiny state-based router
├── app.json                    Expo config (iOS bundle id, motion usage string)
├── babel.config.js
├── index.ts                    registerRootComponent entry
├── package.json
├── tsconfig.json
├── README.md                   ← you are here
└── src/
    ├── config.ts               API_BASE_URL / WEB_APP_URL
    ├── navigation.ts           Screen union type
    ├── theme.ts                Colors / spacing / typography (dark)
    ├── components/
    │   └── BigButton.tsx       Min 56 px, accessible button
    ├── lib/
    │   ├── api.ts              axios upload + error formatter
    │   └── csv.ts              CSV writer + fflate ZIP + base64 encoder
    └── screens/
        ├── HomeScreen.tsx
        ├── RecordScreen.tsx     idle → requesting-permissions → ready
        │                        → recording → stopping → (hand off)
        ├── UploadScreen.tsx     uploading → done | error
        └── ResultsScreen.tsx    polls /api/session/<id>
```

## Recording state machine

```
idle → requesting-permissions → ready → recording → stopping
                                                       ↓
                                  (hands off to UploadScreen)
                                                       ↓
                                           uploading → done | error
```

- `stopping` covers CSV + ZIP build + base64 file write (synchronous on
  the JS thread except for the FS write); the UI shows a "Processing…"
  state.
- The hardware back button (Android) and the in-screen "Back" button are
  both blocked during `recording` and `stopping` so the session can't be
  lost mid-record.

## Type checking

```bash
npm run tsc
```

## Troubleshooting

- **"Network error reaching http://localhost:8000"** on a physical phone:
  set `API_BASE_URL` in `src/config.ts` to your dev Mac's LAN IP, restart
  Expo (`npx expo start --clear`), and confirm the backend is reachable in
  the phone's Safari at `http://<lan-ip>:8000/docs`.
- **No samples captured**: motion permission is denied. Use the
  in-app "Request Permission" button or enable in iOS Settings.
- **GPS samples stay at 0**: location permission is denied or the device has
  no GPS lock yet (cold start can take 30–60 s outdoors). Recording still
  works; the warning banner on the Record screen explains the limitation.
- **Barometer samples stay at 0**: device has no barometer (rare on modern
  phones, but possible on older Androids and iPhones older than the iPhone 6).
  The pipeline degrades gracefully: `segment_runs()` falls back to a single
  skiing run when `relativeAltitude` is missing.
- **Upload says "not a valid ZIP archive"**: the backend now has an
  `unzip` fallback for iOS-style ZIPs (`backend/routes/upload.py`); make sure
  your backend is on a recent commit. The recorder builds ZIPs with `fflate`
  which produce a clean Info-ZIP-style archive.
