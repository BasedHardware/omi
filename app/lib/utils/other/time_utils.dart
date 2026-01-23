import 'package:flutter/widgets.dart';
import 'package:omi/l10n/app_localizations.dart';

String secondsToHumanReadable(int seconds, [BuildContext? context]) {
  final l10n = context != null ? AppLocalizations.of(context) : null;

  if (seconds < 60) {
    if (l10n != null) {
      return seconds == 1 ? l10n.timeSecsSingular(seconds) : l10n.timeSecsPlural(seconds);
    }
    return '$seconds secs';
  } else if (seconds < 3600) {
    var minutes = (seconds / 60).floor();
    var remainingSeconds = seconds % 60;
    if (remainingSeconds == 0) {
      if (l10n != null) {
        return minutes == 1 ? l10n.timeMinSingular(minutes) : l10n.timeMinsPlural(minutes);
      }
      if (minutes == 1) {
        return '$minutes min';
      }
      return '$minutes mins';
    } else {
      if (l10n != null) {
        return l10n.timeMinsAndSecs(minutes, remainingSeconds);
      }
      return '$minutes mins $remainingSeconds secs';
    }
  } else if (seconds < 86400) {
    var hours = (seconds / 3600).floor();
    var remainingMinutes = (seconds % 3600 / 60).floor();
    if (remainingMinutes == 0) {
      if (l10n != null) {
        return hours == 1 ? l10n.timeHourSingular(hours) : l10n.timeHoursPlural(hours);
      }
      if (hours == 1) {
        return '$hours hour';
      }
      return '$hours hours';
    } else {
      if (l10n != null) {
        return l10n.timeHoursAndMins(hours, remainingMinutes);
      }
      return '$hours hours $remainingMinutes mins';
    }
  } else {
    var days = (seconds / 86400).floor();
    var remainingHours = (seconds % 86400 / 3600).floor();
    if (remainingHours == 0) {
      if (l10n != null) {
        return days == 1 ? l10n.timeDaySingular(days) : l10n.timeDaysPlural(days);
      }
      if (days == 1) {
        return '$days day';
      }
      return '$days days';
    } else {
      if (l10n != null) {
        return l10n.timeDaysAndHours(days, remainingHours);
      }
      return '$days days $remainingHours hours';
    }
  }
}

/// Returns a compact representation of seconds (e.g., "10s", "5m", "2h 15m")
/// Designed for use in small UI elements like list items
String secondsToCompactDuration(int seconds, [BuildContext? context]) {
  final l10n = context != null ? AppLocalizations.of(context) : null;

  if (seconds < 60) {
    if (l10n != null) {
      return l10n.timeCompactSecs(seconds);
    }
    return '${seconds}s';
  } else if (seconds < 3600) {
    var minutes = (seconds / 60).floor();
    var remainingSeconds = seconds % 60;
    if (remainingSeconds == 0 || minutes >= 10) {
      if (l10n != null) {
        return l10n.timeCompactMins(minutes);
      }
      return '${minutes}m';
    } else {
      // Only show seconds for durations less than 10 minutes
      if (l10n != null) {
        return l10n.timeCompactMinsAndSecs(minutes, remainingSeconds);
      }
      return '${minutes}m ${remainingSeconds}s';
    }
  } else {
    var hours = (seconds / 3600).floor();
    var remainingMinutes = (seconds % 3600 / 60).floor();
    if (remainingMinutes == 0 || hours >= 10) {
      if (l10n != null) {
        return l10n.timeCompactHours(hours);
      }
      return '${hours}h';
    } else {
      if (l10n != null) {
        return l10n.timeCompactHoursAndMins(hours, remainingMinutes);
      }
      return '${hours}h ${remainingMinutes}m';
    }
  }
}

// convert seconds to hh:mm:ss format
String secondsToHMS(int seconds) {
  var hours = (seconds / 3600).floor();
  var minutes = (seconds % 3600 / 60).floor();
  var remainingSeconds = seconds % 60;
  return '$hours:$minutes:$remainingSeconds';
}
