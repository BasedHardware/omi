import 'dart:async';
import 'dart:isolate';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api_fallback.dart';

/// Times [offUiIsolate] fell back to inline because its input could not cross
/// isolates.
@visibleForTesting
int offUiIsolateFallbacks = 0;

/// Completed worker runs, so default-path tests prove work was offloaded rather
/// than merely exercising an injected test implementation.
@visibleForTesting
int offUiIsolateWorkerCompletions = 0;

/// Runs CPU-bound, pure [work] (JSON encode/decode, hashing, parsing) on a
/// background isolate when its input is large, and inline when it is small.
///
/// The UI isolate builds, lays out and paints every frame. Anything that grows
/// with the user's history (the WAL index, a live transcript, a conversation
/// page with transcripts) must not be encoded or parsed there: at a few
/// thousand records it costs hundreds of milliseconds and the app stutters
/// while syncing. Spawning an isolate costs a few milliseconds, so small inputs
/// stay inline.
///
/// [work] must be pure: it may run twice (once on a background isolate and
/// once inline) when its captured values cannot cross isolates, and it must
/// not touch plugins, platform channels or global mutable state.
/// If [work] itself throws an [ArgumentError] it is retried once inline, which
/// rethrows the same error. `.github/scripts/check_mobile_ui_isolate.py`
/// ratchets the raw alternatives.
Future<R> offUiIsolate<R>(
  R Function() work, {
  required int size,
  required int threshold,
  String debugName = 'offUiIsolate',
}) async {
  if (kIsWeb || size < threshold) return work();
  try {
    final result = await Isolate.run(work, debugName: debugName);
    offUiIsolateWorkerCompletions++;
    return result;
  } on ArgumentError {
    // A captured value was not sendable. Correctness beats latency, but tests
    // assert this stays at zero so the work does not silently move back.
    offUiIsolateFallbacks++;
    // Mode change (background -> UI isolate): report it per the fallback contract.
    recordFallback(const ApiFallbackEvent(reason: ApiFallbackReason.error, outcome: ApiFallbackOutcome.degraded));
    return work();
  }
}
