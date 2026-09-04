final class LimitlessSyncPresentation {
  const LimitlessSyncPresentation._({
    required this.isVisible,
    required this.canOffloadDevice,
    required this.showsCloudProgress,
    required this.showsFlashDrainProgress,
  });

  final bool isVisible;
  final bool canOffloadDevice;
  final bool showsCloudProgress;
  final bool showsFlashDrainProgress;

  factory LimitlessSyncPresentation.resolve({
    required bool hasPendingFlashPages,
    required bool isCloudUploading,
    required bool isFlashDraining,
  }) {
    return LimitlessSyncPresentation._(
      isVisible: hasPendingFlashPages || isCloudUploading || isFlashDraining,
      canOffloadDevice: hasPendingFlashPages && !isFlashDraining,
      showsCloudProgress: isCloudUploading,
      showsFlashDrainProgress: isFlashDraining,
    );
  }
}
