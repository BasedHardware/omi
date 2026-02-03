# Disconnect Issue A/B Comparison Report

## Test Configuration
- **Device:** Pixel 7a
- **Android Version:** 16
- **Duration:** 120s per branch
- **Date:** 2026-02-03

## Versions Compared
- **Build 659:** Commit 071968072 (reported disconnect issues)
- **Main Branch:** Current with battery drain fixes

## Results Summary

| Metric | Build 659 | Main Branch | Delta |
|--------|-----------|-------------|-------|
| Total Segments | 33 | 20 | -13 |
| Total Disconnects | 0 | 0 | 0 |
| Total Connects | 1 | 1 | 0 |
| Avg CPU (active) | ~30-40% | ~100-117% | +60-77% |

## Key Findings

### 1. No Disconnects Observed
Neither version showed any disconnects during the 2-minute test session on Pixel 7a.
The reported "constant disconnects" issue may be:
- Device-specific (Samsung SM-F966U1 vs Pixel 7a)
- Intermittent / requires longer testing period
- Triggered by specific conditions not reproduced

### 2. CPU Usage Regression on Main Branch
**UNEXPECTED:** Main branch shows significantly higher CPU usage (~100-117%) compared to Build 659 (~30-40%).
This is counterintuitive given the battery drain fixes (#4440) merged after Build 659.

Possible causes:
- Additional features/functionality added (OmiGlass support, etc.)
- Shimmer animations still causing overhead
- Metrics/monitoring overhead from Selector pattern changes

### 3. Segment Processing
Build 659 processed more segments (33 vs 20), possibly due to:
- Backend timing differences
- Different conversation patterns
- More efficient processing allowing more segments

## Recommendations

1. **Reproduce on Samsung SM-F966U1** - The disconnect issue may be device-specific
2. **Investigate CPU regression** - Profile main branch to identify the source of increased CPU usage
3. **Extend test duration** - Run longer tests (10+ minutes) to catch intermittent disconnects
4. **Add Shimmer profiling** - Verify Shimmer optimization from #4440 is working

## Raw Data
- `build_659_events.log` - Profiling events from Build 659
- `main_branch_events.log` - Profiling events from main branch
