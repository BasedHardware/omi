/// Backward-compatible alias for [StreamSessionState].
///
/// Kept for one release after v0.1.0 so existing host apps can upgrade
/// incrementally. New code should use [StreamSessionState] directly.
@Deprecated(
    'Use StreamSessionState instead — this alias will be removed in v0.2.0.')
library;

import 'package:meta_wearables_dat_flutter/src/models/stream_session_state.dart';

/// Backward-compatible alias for [StreamSessionState].
///
/// Use [StreamSessionState] in new code.
@Deprecated(
    'Use StreamSessionState instead — this alias will be removed in v0.2.0.')
typedef SessionState = StreamSessionState;
