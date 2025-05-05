String secondsToHumanReadable(int seconds) {
  if (seconds < 60) {
    return '$seconds secs';
  } else if (seconds < 3600) {
    var minutes = (seconds / 60).floor();
    var remainingSeconds = seconds % 60;
    if (remainingSeconds == 0) {
      if (minutes == 1) {
        return '$minutes min';
      }
      return '$minutes mins';
    } else {
      return '$minutes mins $remainingSeconds secs';
    }
  } else if (seconds < 86400) {
    var hours = (seconds / 3600).floor();
    var remainingMinutes = (seconds % 3600 / 60).floor();
    if (remainingMinutes == 0) {
      if (hours == 1) {
        return '$hours hour';
      }
      return '$hours hours';
    } else {
      return '$hours hours $remainingMinutes mins';
    }
  } else {
    var days = (seconds / 86400).floor();
    var remainingHours = (seconds % 86400 / 3600).floor();
    if (remainingHours == 0) {
      if (days == 1) {
        return '$days day';
      }
      return '$days days';
    } else {
      return '$days days $remainingHours hours';
    }
  }
}

/// Returns a compact representation of seconds (e.g., "10s", "5m", "2h 15m")
/// Designed for use in small UI elements like list items
String secondsToCompactDuration(int seconds) {
  if (seconds < 60) {
    return '${seconds}s';
  } else if (seconds < 3600) {
    var minutes = (seconds / 60).floor();
    var remainingSeconds = seconds % 60;
    if (remainingSeconds == 0 || minutes >= 10) {
      return '${minutes}m';
    } else {
      // Only show seconds for durations less than 10 minutes
      return '${minutes}m ${remainingSeconds}s';
    }
  } else {
    var hours = (seconds / 3600).floor();
    var remainingMinutes = (seconds % 3600 / 60).floor();
    if (remainingMinutes == 0 || hours >= 10) {
      return '${hours}h';
    } else {
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
