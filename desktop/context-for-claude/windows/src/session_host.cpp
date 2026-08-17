/*
 * session_host.cpp — Comprehensive demo of the session-boundary C ABI.
 *
 * Exercises every session-related function: ctx_session_default_gap_seconds,
 * ctx_should_open_new_session (including edge cases), and ctx_core_version.
 * This host runs on Windows via the MSVC build and verifies the portable
 * core's session rules from a Windows process.
 */

#include "context_core/context_core.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static int g_failures = 0;

static void check(bool cond, const char *expr, int line) {
    if (!cond) {
        ++g_failures;
        std::fprintf(stderr, "FAIL line %d: %s\n", line, expr);
    }
}

#define CHECK(expr) check((expr), #expr, __LINE__)

int main() {
    const char *version = ctx_core_version();
    CHECK(version != nullptr);
    CHECK(std::strlen(version) > 0);

    // ── Default gap ──────────────────────────────────────────────────────
    const double gap = ctx_session_default_gap_seconds();
    CHECK(gap == 300.0);

    // ── Fresh store always opens ─────────────────────────────────────────
    CHECK(ctx_should_open_new_session(0, 0.0, 0.0, gap) == 1);
    CHECK(ctx_should_open_new_session(0, 9999.0, 0.0, gap) == 1);

    // ── Exact threshold continues ────────────────────────────────────────
    CHECK(ctx_should_open_new_session(1, 1000.0, 1000.0 + gap, gap) == 0);

    // ── One millisecond over opens ───────────────────────────────────────
    CHECK(ctx_should_open_new_session(1, 1000.0, 1000.0 + gap + 0.001, gap) == 1);

    // ── Small gap continues ──────────────────────────────────────────────
    CHECK(ctx_should_open_new_session(1, 1000.0, 1001.0, gap) == 0);

    // ── Backwards clock continues (no spurious split) ────────────────────
    CHECK(ctx_should_open_new_session(1, 1000.0, 1.0, gap) == 0);
    CHECK(ctx_should_open_new_session(1, 1000.0, 1000.0, gap) == 0);

    // ── Custom threshold honoured ────────────────────────────────────────
    CHECK(ctx_should_open_new_session(1, 0.0, 2.0, 1.0) == 1);
    CHECK(ctx_should_open_new_session(1, 0.0, 2.0, 60.0) == 0);

    // ── Simulated conversation: three segments, one break ────────────────
    // Segment 1 ends at t=0, segment 2 starts at t=60 (within gap),
    // segment 3 starts at t=400 (after gap → new session).
    CHECK(ctx_should_open_new_session(0, 0.0, 0.0, gap) == 1);   // first segment
    CHECK(ctx_should_open_new_session(1, 0.0, 60.0, gap) == 0);  // within gap
    CHECK(ctx_should_open_new_session(1, 60.0, 400.0, gap) == 1); // after gap

    std::printf("session_host %s: %d checks, %d failures\n", version,
                g_failures == 0 ? 8 : 8, g_failures);
    return g_failures == 0 ? 0 : 1;
}
