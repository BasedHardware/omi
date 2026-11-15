import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';

/// A cooldown always reads as a cooldown. Mapping any reason to the neutral
/// ready-count copy leaves a stalled sync looking like normal pending work,
/// which is how #10948 stayed invisible for a full day.
String syncCooldownTitle(RateLimitReason? reason, AppLocalizations l) => switch (reason) {
      RateLimitReason.backendBusy => l.syncCardBackendBusy,
      RateLimitReason.dispatchHold => l.syncCardUploadsPaused,
      RateLimitReason.edgeThrottle => l.syncCardThrottlePaused,
      _ => l.syncCardRateLimited,
    };
