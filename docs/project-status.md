# ski-ai Project Status

*Short, high-signal status doc. If you’re looking for details, follow the links.*

## Where to look (source of truth)

- **Master plan / roadmap / security / research protocol**: [`docs/MASTER_PLAN.md`](MASTER_PLAN.md)
- **System architecture (technical)**: [`docs/architecture.md`](architecture.md)
- **API endpoints (just the endpoints)**: [`docs/api.md`](api.md)
- **Algorithm assumptions + thresholds ledger**: [`docs/algorithm-spec.md`](algorithm-spec.md)
- **Research synthesis + engineering implications**: [`docs/research/`](research/)
- **Data formats (raw + processed)**: [`docs/data.md`](data.md)

## Current state (April 2026)

- **Mobile app**: Expo recorder/uploader in `mobile/` records **exactly four sensors**
  (accel, gyro, GPS, barometer) and displays results inside the app.
- **Backend**: FastAPI + RQ worker on Redis; upload → enqueue → process → `report.json`.
- **Algorithm**: Butterworth filter **order = 4**, cutoff **5 Hz**, downsample to **20 Hz**.

## Immediate gaps (next work)

- **Real-data regression**: There is currently **no raw Sensor Logger session folder**
  checked into `data/` (only stale processed outputs). We need a fresh real session
  to regression-test turn counts and metric ranges across algorithm changes.
- **Auth**: No user/device auth; everything is unauthenticated today.
  (Planned device-token beta auth in the master plan.)
