import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/widgets/conversations_group_widget.dart';
import 'package:omi/pages/conversations/widgets/recording_group_list_item.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/ui.dart';

const session = '0123456789abcdef0123456789abcdef';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  for (final brightness in Brightness.values) {
    testWidgets('one Home row retains access to all Watch parts at 200% in $brightness', (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final directory = (await tester.runAsync(() => Directory.systemTemp.createTemp('watch_session_ui')))!;
      addTearDown(() => directory.delete(recursive: true));
      SharedPreferences.setMockInitialValues({'uid': 'watch-owner', 'batchAudioDir': directory.path});
      await SharedPreferencesUtil.init();
      final receipts = (await tester.runAsync(() => Directory('${directory.path}/.watch-receipts').create()))!;
      final names = <String>[];
      final start = DateTime(2026, 10, 21, 23, 50).millisecondsSinceEpoch ~/ 1000;
      await tester.runAsync(() async {
        for (var index = 0; index < 40; index++) {
          final time = start + index * 60;
          final name = 'audio_omibatchwatch${session}s${index}_pcm16_16000_1_fs160_$time.bin';
          names.add(name);
          await File('${directory.path}/$name').writeAsBytes([64, 1, 0, 0, ...List.filled(320, 0)]);
          await File('${receipts.path}/$name').writeAsString(jsonEncode({
            'metadata': {
              'version': 1,
              'sessionID': session,
              'segment': index,
              'startedAt': time,
              'ownerUID': 'watch-owner'
            },
            'digest': List.filled(64, 'a').join(),
          }));
        }
      });
      late LocalRecordingsProvider provider;
      await tester.runAsync(() async {
        provider = _SavedRecordings();
        await provider.refresh();
      });
      addTearDown(provider.dispose);
      expect(provider.recordings, hasLength(40));
      expect(provider.homeRecordings, hasLength(1));
      expect(identical(provider.homeRecordings, provider.homeRecordings), isTrue);

      OmiColors.active = OmiColors.forBrightness(brightness);
      await tester.pumpWidget(ChangeNotifierProvider<LocalRecordingsProvider>.value(
        value: provider,
        child: MaterialApp(
          theme: buildOmiTheme(brightness: brightness),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) =>
              MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(2)), child: child!),
          home: Scaffold(
            body: SingleChildScrollView(
              child: ConversationsGroupWidget(
                  conversations: const [],
                  recordings: provider.recordings,
                  date: DateTime(2026, 10, 21),
                  isFirst: true),
            ),
          ),
        ),
      ));
      await tester.pump();
      expect(find.byType(RecordingGroupListItem), findsOneWidget);
      expect(find.byType(RecordingListItem), findsNothing);
      expect(tester.takeException(), isNull);

      await tester.tap(find.byKey(const ValueKey('watch_session_watch_$session')));
      await tester.pumpAndSettle();
      expect(find.byType(WatchRecordingSessionPage), findsOneWidget);
      final list = tester.widget<ListView>(find.byKey(const ValueKey('watch_session_recordings')));
      expect(list.childrenDelegate.estimatedChildCount, 40);
      await tester.tap(find.byKey(ValueKey(names.first)));
      await tester.pumpAndSettle();
      expect(find.byType(OmiCloseButton), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byType(OmiCloseButton));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.byKey(ValueKey(names.last)), 600,
          scrollable: find.descendant(
              of: find.byKey(const ValueKey('watch_session_recordings')), matching: find.byType(Scrollable)));
      expect(find.byKey(ValueKey(names.last)), findsOneWidget);
      expect(tester.takeException(), isNull);

      provider.clearUserData();
      await tester.pump();
      expect(find.text('No Recordings'), findsOneWidget);
      expect(provider.homeRecordings, isEmpty);
      expect(await tester.runAsync(() => File('${directory.path}/${names.first}').exists()), isTrue,
          reason: 'changing account clears presentation, never the saved audio');
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}

// Keep the real directory/receipt scan and account custody. Waveform decoding
// belongs to the native audio boundary and is exercised in the simulator probe.
class _SavedRecordings extends LocalRecordingsProvider {
  @override
  Future<List<double>?> getWaveform(LocalRecording recording) async => const [];
}
