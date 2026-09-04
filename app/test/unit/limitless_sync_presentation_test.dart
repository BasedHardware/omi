import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/capture/widgets/limitless_sync_presentation.dart';

void main() {
  test('cloud upload does not hide or disable device offload', () {
    final state = LimitlessSyncPresentation.resolve(
      hasPendingFlashPages: true,
      isCloudUploading: true,
      isFlashDraining: false,
    );

    expect(state.isVisible, isTrue);
    expect(state.canOffloadDevice, isTrue);
    expect(state.showsCloudProgress, isTrue);
  });

  test('only an active flash drain disables the offload action', () {
    final state = LimitlessSyncPresentation.resolve(
      hasPendingFlashPages: true,
      isCloudUploading: true,
      isFlashDraining: true,
    );

    expect(state.canOffloadDevice, isFalse);
    expect(state.showsFlashDrainProgress, isTrue);
  });

  test('card hides when neither device work nor upload work exists', () {
    final state = LimitlessSyncPresentation.resolve(
      hasPendingFlashPages: false,
      isCloudUploading: false,
      isFlashDraining: false,
    );

    expect(state.isVisible, isFalse);
  });
}
