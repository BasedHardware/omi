import 'package:omi/l10n/app_localizations.dart';

/// The one way to put a length of time on screen (docs/ux-contract.md §8).
///
/// | Style      | Examples                  | Use                                                     |
/// |------------|---------------------------|---------------------------------------------------------|
/// | [offset]   | 0:05 · 3:38 · 1:02:05     | a position inside a recording, or time remaining        |
/// | [compact]  | 8s · 4m 10s · 42m · 1h 5m | a conversation's or recording's length, list and detail |
/// | [long]     | 42 mins 10 secs           | accessibility labels and sentences                      |
///
/// A list row and the detail page of the same thing use the same style ([compact]), so they
/// always agree.
abstract final class OmiDuration {
  /// A clock-style position: `m:ss` under an hour, `h:mm:ss` from an hour. Never drops the hours.
  static String offset(num seconds) {
    final total = seconds.isFinite && seconds > 0 ? seconds.floor() : 0;
    final hours = total ~/ 3600;
    final minutes = (total % 3600) ~/ 60;
    final secs = total % 60;
    final ss = secs.toString().padLeft(2, '0');
    if (hours > 0) return '$hours:${minutes.toString().padLeft(2, '0')}:$ss';
    return '$minutes:$ss';
  }

  /// A length in the fewest units that still read precisely: seconds under a minute, minutes and
  /// seconds under ten minutes, whole minutes under an hour, hours and minutes under ten hours,
  /// whole hours after that. Units are localized when [l10n] is given.
  static String compact(int seconds, [AppLocalizations? l10n]) {
    final total = seconds < 0 ? 0 : seconds;
    if (total < 60) return l10n?.timeCompactSecs(total) ?? '${total}s';
    if (total < 3600) {
      final minutes = total ~/ 60;
      final secs = total % 60;
      if (secs == 0 || minutes >= 10) return l10n?.timeCompactMins(minutes) ?? '${minutes}m';
      return l10n?.timeCompactMinsAndSecs(minutes, secs) ?? '${minutes}m ${secs}s';
    }
    final hours = total ~/ 3600;
    final minutes = (total % 3600) ~/ 60;
    if (minutes == 0 || hours >= 10) return l10n?.timeCompactHours(hours) ?? '${hours}h';
    return l10n?.timeCompactHoursAndMins(hours, minutes) ?? '${hours}h ${minutes}m';
  }

  /// A length spelled out ("12 mins 34 secs", "2 hours 5 mins", "3 days 4 hours"), for screen
  /// readers and running text. Falls back to English only when no [l10n] is available.
  static String long(int seconds, [AppLocalizations? l10n]) {
    final total = seconds < 0 ? 0 : seconds;
    if (total < 60) {
      if (l10n != null) return total == 1 ? l10n.timeSecsSingular(total) : l10n.timeSecsPlural(total);
      return '$total secs';
    }
    if (total < 3600) {
      final minutes = total ~/ 60;
      final secs = total % 60;
      if (secs == 0) {
        if (l10n != null) return minutes == 1 ? l10n.timeMinSingular(minutes) : l10n.timeMinsPlural(minutes);
        return minutes == 1 ? '$minutes min' : '$minutes mins';
      }
      return l10n?.timeMinsAndSecs(minutes, secs) ?? '$minutes mins $secs secs';
    }
    if (total < 86400) {
      final hours = total ~/ 3600;
      final minutes = (total % 3600) ~/ 60;
      if (minutes == 0) {
        if (l10n != null) return hours == 1 ? l10n.timeHourSingular(hours) : l10n.timeHoursPlural(hours);
        return hours == 1 ? '$hours hour' : '$hours hours';
      }
      return l10n?.timeHoursAndMins(hours, minutes) ?? '$hours hours $minutes mins';
    }
    final days = total ~/ 86400;
    final hours = (total % 86400) ~/ 3600;
    if (hours == 0) {
      if (l10n != null) return days == 1 ? l10n.timeDaySingular(days) : l10n.timeDaysPlural(days);
      return days == 1 ? '$days day' : '$days days';
    }
    return l10n?.timeDaysAndHours(days, hours) ?? '$days days $hours hours';
  }
}
