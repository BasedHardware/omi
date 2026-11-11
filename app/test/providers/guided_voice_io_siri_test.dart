import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/pages/onboarding/guided_voice_io.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/siri_integration.dart';

class _MemoryHost extends SiriIndexApi {
  final rows = <String, SiriMemory>{};

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> memories) async {
    for (final row in memories) {
      rows[row.id] = row;
    }
  }
}

/// Logs call order instead of just final state, so a test can tell "stop
/// landed before the recorder actually started" from "stop landed after".
class _FakeMic implements IMicRecorderService {
  final startGate = Completer<void>();
  final events = <String>[];

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
    Function(bool began)? onInterruption,
  }) async {
    events.add('start-called');
    await startGate.future;
    events.add('started');
  }

  @override
  Future<void> startBatch({
    Function()? onStop,
    Function(bool began)? onInterruption,
    Function()? onBatchStalled,
    Function(String code, String message)? onError,
  }) async {}

  @override
  void stop() => events.add('stop-called');

  @override
  void probeStallAfterForeground() {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'guided-owner'});
    await SharedPreferencesUtil.init();
  });

  test('confirmed guided onboarding memory reaches the Siri snapshot', () async {
    final host = _MemoryHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'guided-owner');
    addTearDown(() => SiriIntegration.testInstance = null);
    final memory = Memory(
        id: 'guided-1',
        uid: 'guided-owner',
        content: 'I like coffee',
        category: MemoryCategory.system,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final io = DeviceGuidedVoiceIO(createMemoryRequest: (_, __, ___) async => memory);

    expect(await io.remember('I like coffee'), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.rows['guided-1']?.content, 'I like coffee');
  });

  test('a stop that lands while the recorder is still starting stops it once it starts', () async {
    final mic = _FakeMic();
    final io = DeviceGuidedVoiceIO(mic: mic);
    final starting = io.start((_) {}, () {});
    await io.stop();
    mic.startGate.complete();
    await starting;
    expect(mic.events, ['start-called', 'started', 'stop-called']);
  });

  test('start and stop without overlap behaves normally', () async {
    final mic = _FakeMic()..startGate.complete();
    final io = DeviceGuidedVoiceIO(mic: mic);
    await io.start((_) {}, () {});
    await io.stop();
    expect(mic.events, ['start-called', 'started', 'stop-called']);
  });
}
