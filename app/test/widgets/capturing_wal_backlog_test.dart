import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get connectedDevice => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubConnectivityProvider extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

/// Session WALs for the live-capture indicator: [unsynced] feeds the duration
/// line, [all] the pending/total count.
class _PhoneSync {
  _PhoneSync({this.unsynced = const [], this.all = const []});

  final List<Wal> unsynced;
  final List<Wal> all;

  int getInFlightSeconds() => 0;

  List<Wal> getSessionUnsyncedWals(int start) => unsynced;

  List<Wal> getSessionWals(int start) => all;

  Future<void> finalizeCurrentSession() async {}

  Future<void> stampConversationId(int start, String id) async {}
}

class _Wal implements IWalService {
  _Wal(this.phone);

  final _PhoneSync phone;

  @override
  dynamic getSyncs() => _Syncs(phone);

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Syncs {
  _Syncs(this.phone);

  final _PhoneSync phone;
}

class _BacklogCaptureProvider extends CaptureProvider {
  _BacklogCaptureProvider(_PhoneSync phone)
      : super(
          walService: _Wal(phone),
          connectivity: CaptureConnectivityBoundary(
            initiallyConnected: true,
            changes: const Stream.empty(),
            isConnected: () => true,
          ),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );
}

Wal _wal(int timerStart, {WalStatus status = WalStatus.miss, int seconds = 60}) {
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: seconds,
    status: status,
    storage: WalStorage.disk,
    device: 'omi',
    filePath: 'indicator_$timerStart.bin',
  );
}

TranscriptSegment _segment() {
  return TranscriptSegment(
    id: 'seg-1',
    text: 'hello',
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0.0,
    end: 1.0,
    translations: [],
  );
}

Future<void> _pumpCapturingPage(WidgetTester tester, CaptureProvider capture) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final device = _StubDeviceProvider();
  final connectivity = _StubConnectivityProvider();
  final usage = UsageProvider();
  addTearDown(device.dispose);
  addTearDown(connectivity.dispose);
  addTearDown(usage.dispose);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
      ],
      child: MaterialApp(
        theme: ThemeData.dark(),
        locale: const Locale('en'),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: const ConversationCapturingPage(),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a draining queue shows pending X/Y next to the audio line', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final pending = [_wal(now - 100), _wal(now - 80), _wal(now - 60)];
    final uploaded = List.generate(6, (i) => _wal(now - 40 + i, status: WalStatus.synced));
    final capture = _BacklogCaptureProvider(_PhoneSync(unsynced: pending, all: [...pending, ...uploaded]));
    capture
      ..testSessionStartSeconds = now - 120
      ..segments = [_segment()];
    addTearDown(capture.dispose);

    await _pumpCapturingPage(tester, capture);

    expect(find.text('Transcriptions pending 3/9'), findsOneWidget);
    expect(find.textContaining('audio saved locally'), findsOneWidget);
  });

  testWidgets('a single queued recording keeps the duration line only', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final capture = _BacklogCaptureProvider(_PhoneSync(unsynced: [_wal(now - 60)], all: [_wal(now - 60)]));
    capture
      ..testSessionStartSeconds = now - 120
      ..segments = [_segment()];
    addTearDown(capture.dispose);

    await _pumpCapturingPage(tester, capture);

    expect(find.textContaining('Transcriptions pending'), findsNothing);
    expect(find.textContaining('audio saved locally'), findsOneWidget);
  });
}
