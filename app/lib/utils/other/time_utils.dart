import 'package:flutter/widgets.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/omi_duration.dart';

/// Spelled-out length ("12 mins 34 secs"). Delegates to [OmiDuration.long]; new code calls that
/// (and uses [OmiDuration.compact] for lengths shown in rows and details).
String secondsToHumanReadable(int seconds, [BuildContext? context]) =>
    OmiDuration.long(seconds, context != null ? AppLocalizations.of(context) : null);

/// Compact length ("10s", "5m", "2h 15m"). Delegates to [OmiDuration.compact]; new code calls that.
String secondsToCompactDuration(int seconds, [BuildContext? context]) =>
    OmiDuration.compact(seconds, context != null ? AppLocalizations.of(context) : null);

/// Clock-style position ("3:38", "1:02:05"). Delegates to [OmiDuration.offset].
///
/// It used to print unpadded `h:m:s` ("0:3:8"); it has no callers that depend on that shape.
String secondsToHMS(int seconds) => OmiDuration.offset(seconds);
