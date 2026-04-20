# Omi Performance Tests

Automated performance testing framework for the Omi Flutter app.

## Architecture

```
app/
├── integration_test/
│   └── performance_suite_test.dart   # Integration perf tests (FPS, startup, memory)
├── test/performance/
│   ├── perf_metrics_collector.dart   # Metrics collection utility
│   ├── leak_tracking_config.dart     # Memory leak detection setup
│   └── README.md                     # This file
├── scripts/
│   └── run_performance_tests.sh      # Runner with reporting
└── perf_reports/                     # Generated reports (gitignored)
```

## What's Measured

| Metric | Target | Method |
|--------|--------|--------|
| Cold start time | < 5s | Stopwatch from app launch to first frame |
| Scroll FPS | 60fps (no jank) | `traceAction` + Chrome trace analysis |
| Tab switch latency | < 300ms | Stopwatch around navigation |
| Memory growth | < 10MB/hour | Repeated navigation cycles |
| Chat response time | < 10s | End-to-end message round trip |
| Memory leaks | 0 detected | leak_tracker integration |

## Running

```bash
# Quick run (5 min, basic metrics)
cd app && bash scripts/run_performance_tests.sh

# Extended run (1 hour, includes battery monitoring)
bash scripts/run_performance_tests.sh --duration 1h

# Just the integration tests
flutter test integration_test/performance_suite_test.dart --profile
```

## Reading Results

After a run, check `perf_reports/`:

- **perf_trace.json** — Open in `chrome://tracing` for frame-by-frame analysis
- **summary.txt** — Quick human-readable overview
- **extended_metrics.csv** — Time-series data (timestamp, memory_kb, cpu_%, battery_%)
- **test_output.log** — Raw test output including leak_tracker warnings

## Adding New Performance Tests

1. Add a `testWidgets` in `performance_suite_test.dart`
2. Use `binding.traceAction()` to capture frame timing
3. Use `Stopwatch` for wall-clock measurements
4. Report metrics via `binding.reportData`

## CI Integration

Performance tests run on every push to `app/` via GitHub Actions.
They don't block PRs but report regressions as comments.
See `.github/workflows/perf-tests.yml`.

## Dependencies

Add to `pubspec.yaml` under `dev_dependencies`:
```yaml
dev_dependencies:
  integration_test:
    sdk: flutter
  leak_tracker: ^10.0.0
```
