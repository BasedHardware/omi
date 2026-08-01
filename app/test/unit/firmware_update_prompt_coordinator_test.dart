import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/firmware_update_prompt_coordinator.dart';

void main() {
  group('FirmwareUpdatePromptCoordinator', () {
    test('Later dismisses immediately and defers only the current version', () {
      final coordinator = FirmwareUpdatePromptCoordinator()..setAvailableVersion('3.0.20');
      final prompt = coordinator.beginPresentation()!;
      var dismissals = 0;
      coordinator.attachDismissal(prompt, () => dismissals++);

      expect(coordinator.defer(prompt), isTrue);
      expect(dismissals, 1);

      coordinator.complete(prompt);
      expect(coordinator.beginPresentation(), isNull);

      coordinator.setAvailableVersion('3.0.21');
      expect(coordinator.beginPresentation(), isNotNull);
    });

    test('cleared availability dismisses an active prompt and permits a legitimate future prompt', () {
      final coordinator = FirmwareUpdatePromptCoordinator()..setAvailableVersion('3.0.20');
      final prompt = coordinator.beginPresentation()!;
      var dismissals = 0;
      coordinator.attachDismissal(prompt, () => dismissals++);

      coordinator.setAvailableVersion(null);

      expect(dismissals, 1);
      coordinator.complete(prompt);
      coordinator.setAvailableVersion('3.0.20');
      expect(coordinator.beginPresentation(), isNotNull);
    });

    test('Update dismisses without deferring the available version', () {
      final coordinator = FirmwareUpdatePromptCoordinator()..setAvailableVersion('3.0.20');
      final prompt = coordinator.beginPresentation()!;
      var dismissals = 0;
      coordinator.attachDismissal(prompt, () => dismissals++);

      expect(coordinator.accept(prompt), isTrue);
      expect(dismissals, 1);

      coordinator.complete(prompt);
      expect(coordinator.beginPresentation(), isNotNull);
    });

    test('stale presentation is dismissed even when its route attaches after invalidation', () {
      final coordinator = FirmwareUpdatePromptCoordinator()..setAvailableVersion('3.0.20');
      final stalePrompt = coordinator.beginPresentation()!;

      coordinator.invalidatePresentation();

      var dismissals = 0;
      coordinator.attachDismissal(stalePrompt, () => dismissals++);
      expect(dismissals, 1);

      coordinator.complete(stalePrompt);
      final freshPrompt = coordinator.beginPresentation();
      expect(freshPrompt, isNotNull);

      coordinator.complete(stalePrompt);
      expect(coordinator.beginPresentation(), isNull);
    });
  });
}
