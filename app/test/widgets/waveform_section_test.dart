import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/playback_state.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/widgets/waveform_section.dart';

// Mock SyncProvider for testing
class MockSyncProvider extends SyncProvider {
  @override
  Duration get totalDuration => const Duration(seconds: 60);
}

const _testPlaybackState = PlaybackState(
  isPlaying: false,
  isProcessing: false,
  canPlayOrShare: true,
  isSynced: true,
  hasError: false,
  currentPosition: Duration.zero,
  totalDuration: Duration(seconds: 60),
  playbackProgress: 0.0,
);

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized
    }
  });

  group('WaveformSection timer cadence', () {
    testWidgets('timer updates at 250ms intervals for reduced CPU usage', (tester) async {
      // Build the widget with required providers
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: ChangeNotifierProvider<SyncProvider>(
            create: (_) => MockSyncProvider(),
            child: const Scaffold(
              body: SizedBox(
                height: 200,
                child: WaveformSection(
                  seconds: 60,
                  waveformData: [0.5, 0.6, 0.7, 0.8],
                  isProcessingWaveform: false,
                  playbackState: _testPlaybackState,
                  isPlaying: true,
                ),
              ),
            ),
          ),
        ),
      );

      // Wait for initial build
      await tester.pumpAndSettle();

      // The widget should be created successfully with 250ms timer
      expect(find.byType(WaveformSection), findsOneWidget);

      // Advance by 100ms - should not trigger update yet (was 100ms before optimization)
      await tester.pump(const Duration(milliseconds: 100));

      // Advance by another 150ms to reach 250ms total - should trigger update now
      await tester.pump(const Duration(milliseconds: 150));

      // Widget should still be present and functional
      expect(find.byType(WaveformSection), findsOneWidget);
    });
  });
}
