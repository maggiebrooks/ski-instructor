# Testing

Unit tests cover all pipeline functions, the analytics layer, biomechanical
scoring, and the metadata system.

```bash
python -m pytest tests/ -v
```

## Test Summary

| Test Class | Tests | What's Covered |
|------------|-------|----------------|
| `TestLoadSensorFile` | 3 | Column renaming, prefix logic, non-xyz columns |
| `TestComputeRowFeatures` | 3 | Correct magnitudes, immutability, zero values |
| `TestPreprocess` | 3 | Downsampling ratio, timestamp generation, LP filter effectiveness |
| `TestDetectTurns` | 4 | Known peaks, negative peaks, flat signal, distance param |
| `TestSegmentRuns` | 5 | Labels exist, descent=skiing, ascent=lift, run_id incrementing, immutability |
| `TestComputeSessionSummary` | 2 | Output structure, JSON file writing |
| `TestDiscoverSessions` | 2 | Valid session detection, empty directory handling |
| `TestComputeTurnMetrics` | 10 | Angle/direction, radius calculation, radius guards (low speed/rotation), symmetry (centered vs offset), edge angle range, pelvis wrapper equivalence, immutability |
| `TestDetectTurnPhases` | 4 | Zero-crossing detection, fallback to boundaries (before/after/short segment) |
| `TestComputeCarvingMetrics` | 5 | Edge build slope, radius CoV, speed loss, guards (zero speed, low rotation), immutability |
| `TestLoadTurns` | 6 | All-turns load, column validation, single/multi session filtering, nonexistent session, empty DB |
| `TestSessionMetrics` | 7 | Key structure, total counts, L/R balance, avg radius, avg speed, session_id passthrough, empty graceful handling |
| `TestCompareSessions` | 5 | DataFrame return type, row-per-session, correct counts, consistency with session_metrics, empty handling |
| `TestRunMetrics` | 5 | DataFrame return, row-per-run, turn counts, avg radius, empty session |
| `TestComputeNormalizedMetrics` | 11 | Pressure ratio physics, torso rotation ratio, normalized radius with/without metadata, zero-radius/angle guards, missing keys |
| `TestComputeMovementScores` | 21 | Six scores in range, too-few/empty guards, rotary stability heuristics, edge consistency, pressure ratio physics, symmetry, rhythm, efficiency, zero-angle handling, metadata threading, backward compat, normalized keys |
| `TestInterpretFundamentals` | 8 | Tier feedback for each score level, None handling, metadata acceptance, value lines, rhythm feedback |
| `TestOutputStructure` | 4 | Turn count header, Fundamental Analysis header, all six headings, value lines per section |
| `TestSessionReport` | 3 | Analyzer integration, metadata pass-through, no-metadata backward compat |
| `TestZeroTurnGuard` | 2 | Zero turns, missing total_turns key |
| `TestLoadSkierProfile` | 3 | Correct load, nested equipment, missing returns None |
| `TestLoadSkiProfile` | 2 | Correct load, missing returns None |
| `TestLoadSessionMetadata` | 2 | Correct load, missing returns None |
| `TestRealProfiles` | 3 | Integration tests against real YAML example files |

**Total: 219 tests.** Tests use synthetic data generated at runtime -- no
dependency on real session files. Backend tests mock Redis so no running
server is needed.

## Test Files

| File | Tests | Scope |
|------|------:|-------|
| `tests/test_backend.py` | 34 | Backend API (upload, sessions, plots, jobs, storage, dedup, metadata) |
| `tests/test_validation.py` | 19 | Input/output validation, data quality flags, confidence |
| `tests/test_physics_validity.py` | 40 | Radius, centripetal, integration, confidence rules, registry |
| `tests/test_turn_insights.py` | 50 | `TurnInsights` (movement scores, normalization, interpretation, session report) |
| `tests/test_pipeline.py` | 41 | Pipeline functions (ingestion, preprocessing, segmentation, turn detection, carving) |
| `tests/test_turn_analyzer.py` | 25 | `TurnAnalyzer` (DB queries, metrics, cross-session comparison) |
| `tests/test_metadata_loader.py` | 10 | `MetadataLoader` (YAML loading, missing file handling, real profiles) |
