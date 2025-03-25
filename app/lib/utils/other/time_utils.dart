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

// convert seconds to hh:mm:ss format
String secondsToHMS(int seconds) {
  var hours = (seconds / 3600).floor();
  var minutes = (seconds % 3600 / 60).floor();
  var remainingSeconds = seconds % 60;
  return '$hours:$minutes:$remainingSeconds';
}
