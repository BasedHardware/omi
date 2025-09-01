class PlaybackState {
  final bool isPlaying;
  final bool isProcessing;
  final bool isSharing;
  final bool canPlayOrShare;
  final bool isSynced;
  final bool hasError;
  final Duration currentPosition;
  final Duration totalDuration;
  final double playbackProgress;

  const PlaybackState({
    required this.isPlaying,
    required this.isProcessing,
    required this.isSharing,
    required this.canPlayOrShare,
    required this.isSynced,
    required this.hasError,
    required this.currentPosition,
    required this.totalDuration,
    required this.playbackProgress,
  });
}
