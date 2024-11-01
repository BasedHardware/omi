class WatchConnectionError extends Error {
  final String message;
  WatchConnectionError(this.message);

  @override
  String toString() => 'WatchConnectionError: $message';
}

class WatchRecordingError extends Error {
  final String message;
  WatchRecordingError(this.message);

  @override
  String toString() => 'WatchRecordingError: $message';
}
