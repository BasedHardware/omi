import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'dart:typed_data';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/on_device/on_device_engine.dart';
import 'package:omi/services/on_device/on_device_runner.dart';
import 'package:omi/services/on_device/on_device_segment_snapshot.dart';
import 'package:omi/services/on_device/on_device_projection.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import '../support/on_device_fakes.dart';
import '../support/refactor_flag_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('omi-overflow-test-');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => directory.path);
  });
  tearDown(() async {
    AnalyticsManager.resetForTesting();
    await directory.delete(recursive: true);
  });

  test('engine selection gates OS and language; Android stays whisper', () {
    OnDeviceEngine select(int version, {bool supported = true, bool english = true}) =>
        selectOnDeviceEngine(ios: true, iosMajor: version, appleLocaleSupported: supported, english: english);
    expect(select(26), OnDeviceEngine.speechAnalyzer);
    expect(select(25), OnDeviceEngine.parakeetV2);
    expect(select(17), OnDeviceEngine.parakeetV2);
    expect(select(16), OnDeviceEngine.sfSpeech);
    expect(select(26, supported: false, english: false), OnDeviceEngine.sfSpeech);
    expect(selectOnDeviceEngine(ios: false, iosMajor: 0, appleLocaleSupported: false, english: true),
        OnDeviceEngine.whisperTiny);
  });

  Future<File> recording({int frames = 6100, bool truncated = false}) async {
    final builder = BytesBuilder();
    for (var i = 0; i < frames; i++) {
      final header = ByteData(4)..setUint32(0, 320, Endian.little);
      builder.add(header.buffer.asUint8List());
      builder.add(Uint8List(320));
    }
    if (truncated) builder.add([5, 0]);
    return File('${directory.path}/synthetic.bin')..writeAsBytesSync(builder.takeBytes());
  }

  test('WAL read is bounded at 30s and rejects truncated custody', () async {
    final file = await recording();
    final counts = await readOnDeviceChunks(file, 100).map((c) => c.length).toList();
    expect(counts, [3000, 3000, 100]);
    final broken = await recording(frames: 1, truncated: true);
    await expectLater(readOnDeviceChunks(broken, 100).toList(), throwsFormatException);
  });

  test('phone-only WALs cannot enter an automatic upload, including flag-off recovery', () {
    final wal = Wal(
        timerStart: 100,
        codec: BleAudioCodec.pcm16,
        seconds: 30,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        onDeviceOnly: true);
    expect(isAutoUploadEligible(wal), isFalse);
    final restored = Wal.fromJson(wal.toJson());
    expect(restored.onDeviceOnly, isTrue);
    expect(isAutoUploadEligible(restored), isFalse);
  });

  test('runner commits a transcript-only conversation and retries safely across runs', () async {
    await recording();
    final wal = Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.pcm16,
        seconds: 61,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        filePath: 'synthetic.bin',
        onDeviceOnly: true);
    final persisted = <Map<String, dynamic>>[];
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (wals) async {
      persisted.add(wals.first.toJson());
    });
    sync.testWals = [wal];
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource());
    controller.debugActivate(settings: const OnDeviceSettings(enabled: true, keepEverythingOnDevice: true));
    var calls = 0;
    final rows = <ServerConversation>[];
    final runner = OnDeviceRunner(
        sync: sync,
        controller: controller,
        publish: rows.add,
        transcribeChunk: (bytes, language) async {
          calls++;
          final duration = (bytes.length - 44) / 32000;
          expect(duration, lessThanOrEqualTo(30));
          return OnDeviceBatchResult(
              engine: 'synthetic',
              text: 'A synthetic test sentence.',
              words: [OnDeviceWord('A synthetic test sentence.', 0, duration)]);
        });
    await runner.run();
    expect(calls, 0); // Charging is the default.
    await runner.run(transcribeNow: true);
    expect(calls, 3);
    expect(rows, hasLength(1));
    expect(persisted, isNotEmpty);
    expect(rows.single.transcriptSegments.map((s) => s.start), [0, 30, 60]);
    expect(OnDeviceProvenance.fromConversation(rows.single)?.summary, OnDeviceSummaryOrigin.none);
    await runner.run(transcribeNow: true);
    expect(calls, 3);
    expect(rows, hasLength(1));
    runner.dispose();
    controller.dispose();
  });

  test('account change during inference cannot commit or publish', () async {
    await recording(frames: 100);
    final wal = Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.pcm16,
        seconds: 1,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        filePath: 'synthetic.bin',
        onDeviceOnly: true);
    var persists = 0;
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {
      persists++;
    });
    sync.testWals = [wal];
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource());
    controller.debugActivate(settings: const OnDeviceSettings(enabled: true, keepEverythingOnDevice: true));
    final rows = <ServerConversation>[];
    final runner = OnDeviceRunner(
        sync: sync,
        controller: controller,
        publish: rows.add,
        transcribeChunk: (_, __) async {
          sync.clearUserData();
          return const OnDeviceBatchResult(engine: 'synthetic', text: 'Test.', words: [OnDeviceWord('Test.', 0, 1)]);
        });
    await runner.run(transcribeNow: true);
    expect(persists, 0);
    expect(rows, isEmpty);
    expect(wal.onDeviceConversation, isNull);
    runner.dispose();
    controller.dispose();
  });

  test('cloud summaries send transcript text, preserve provenance and retry failed ingestion', () async {
    await recording(frames: 100);
    final wal = Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.pcm16,
        seconds: 1,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        filePath: 'synthetic.bin',
        onDeviceOnly: true);
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {});
    sync.testWals = [wal];
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource());
    controller.debugActivate();
    final rows = <ServerConversation>[];
    var unavailable = true;
    final requests = <String>[];
    final cloud = ServerConversation(
        id: 'cloud-synthetic',
        createdAt: DateTime.utc(2026),
        structured: Structured('Synthetic title', 'Synthetic cloud overview'),
        transcriptSegments: [
          TranscriptSegment(
              id: '1',
              text: 'A synthetic test.',
              speaker: 'SPEAKER_00',
              isUser: false,
              personId: null,
              start: 0,
              end: 1,
              translations: const [],
              sttProvider: 'on_device:synthetic')
        ]);
    final runner = OnDeviceRunner(
        sync: sync,
        controller: controller,
        publish: rows.add,
        cloudBaseUrl: 'http://127.0.0.1:1/',
        transcribeChunk: (_, __) async => const OnDeviceBatchResult(
            engine: 'synthetic', text: 'A synthetic test.', words: [OnDeviceWord('A synthetic test.', 0, 1)]),
        send: (request) async {
          requests.add(request.method);
          if (unavailable) return http.Response('', 503);
          if (request.method == 'POST') {
            final body = jsonDecode(request.body) as Map<String, dynamic>;
            expect(body['client_session_id'], startsWith('ondevice-'));
            expect(body['transcript_segments'][0]['stt_provider'], 'on_device:synthetic');
            expect(body.containsKey('audio'), isFalse);
            return http.Response(jsonEncode({'id': cloud.id}), 200);
          }
          return http.Response(jsonEncode(cloud.toJson()), 200);
        });
    await runner.run(transcribeNow: true);
    expect(wal.onDeviceConversation, isNull);
    expect(rows, isEmpty);
    expect(controller.lastRunFailed, isTrue);
    unavailable = false;
    await runner.run(transcribeNow: true);
    expect(requests, ['POST', 'POST', 'GET']);
    expect(rows, hasLength(1));
    expect(OnDeviceProvenance.fromConversation(rows.single)?.summary, OnDeviceSummaryOrigin.cloud);
    expect(controller.lastRunFailed, isFalse);
    runner.dispose();
    controller.dispose();
  });

  for (final count in [10, 501]) {
    test('disabled continuation terminalizes prepared input once without speech or upload ($count)', () async {
      await setRefactorFlags({'clients_from_segments_chunks': false});
      final file = await recording(frames: 100);
      final prepared = OnDeviceSegmentSnapshot(
          segments: List.generate(
              count,
              (i) => TranscriptSegment(
                  id: '$i',
                  text: 'synthetic',
                  speaker: 'SPEAKER_00',
                  isUser: false,
                  personId: null,
                  translations: const [],
                  start: i.toDouble(),
                  end: i + .5)),
          duration: count.toDouble(),
          language: 'en',
          engine: 'synthetic',
          projection: null);
      final wal = Wal(
          timerStart: 1700000000,
          codec: BleAudioCodec.pcm16,
          seconds: 1,
          storage: WalStorage.disk,
          status: WalStatus.miss,
          filePath: 'synthetic.bin',
          onDeviceOnly: true,
          onDevicePreparedUpload: prepared.toJson());
      var saves = 0;
      final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {
        saves++;
      })
        ..testWals = [wal];
      final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource())
        ..debugActivate();
      addTearDown(controller.dispose);
      await controller.model.remove();
      var modelCalls = 0, sends = 0;
      final runner = OnDeviceRunner(
          sync: sync,
          controller: controller,
          publish: (_) {},
          transcribeChunk: (_, __) async {
            modelCalls++;
            throw StateError('must not recognize');
          },
          send: (_) async {
            sends++;
            return http.Response('', 503);
          });
      addTearDown(runner.dispose);
      await runner.run(transcribeNow: true);
      expect(runner.lastError, 'continuation_disabled');
      expect(wal.status, WalStatus.uploadRejected);
      expect(wal.onDevicePreparedUpload, isNull);
      expect(wal.onDeviceUploadFailure, 'continuation_disabled');
      final restored = Wal.fromJson(jsonDecode(jsonEncode(wal.toJson())) as Map<String, dynamic>);
      expect(restored.onDeviceUploadFailure, 'continuation_disabled');
      expect(restored.status, WalStatus.uploadRejected);
      final saved = saves;
      await runner.run(transcribeNow: true);
      expect(saves, saved);
      expect(modelCalls, 0);
      expect(sends, 0);
      expect(await file.exists(), isTrue);
    });
  }
  test('continuation restart reuses the durable transcript without rerunning speech', () async {
    await setRefactorFlags({'clients_from_segments_chunks': true});
    await recording(frames: 100);
    final wal = Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.pcm16,
        seconds: 1,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        filePath: 'synthetic.bin',
        onDeviceOnly: true);
    var saved = <Map<String, dynamic>>[];
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (rows) async {
      saved = rows.map((row) => Map<String, dynamic>.from(row.toJson())).toList();
    })
      ..testWals = [wal];
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource())
      ..debugActivate();
    addTearDown(controller.dispose);
    var modelCalls = 0;
    final posts = <String>[];
    final first = OnDeviceRunner(
        sync: sync,
        controller: controller,
        publish: (_) {},
        cloudBaseUrl: 'http://127.0.0.1:1/',
        transcribeChunk: (_, __) async {
          modelCalls++;
          return OnDeviceBatchResult(
              engine: 'synthetic',
              text: 'synthetic',
              words: List.generate(15030, (i) => OnDeviceWord('synthetic', i / 20000, (i + 1) / 20000)));
        },
        send: (request) async {
          posts.add(request.body);
          final body = jsonDecode(request.body) as Map;
          return http.Response(body['chunk_index'] == 0 ? '{"id":"cloud"}' : '', body['chunk_index'] == 0 ? 200 : 503);
        });
    await first.run(transcribeNow: true);
    expect(controller.lastRunFailed, isTrue);
    expect(wal.onDeviceConversation, isNull);
    expect(wal.onDevicePreparedUpload, isNotNull);
    expect(saved.single['on_device_prepared_upload'], isNotNull);
    first.dispose();
    final restored = Wal.fromJson(jsonDecode(jsonEncode(saved.single)) as Map<String, dynamic>);
    final restarted = LocalWalSyncImpl(_Listener(), persistWals: (_) async {})..testWals = [restored];
    SharedPreferencesUtil().userPrimaryLanguage = 'es';
    await controller.model.remove();
    final rows = <ServerConversation>[];
    final second = OnDeviceRunner(
        sync: restarted,
        controller: controller,
        publish: rows.add,
        cloudBaseUrl: 'http://127.0.0.1:1/',
        transcribeChunk: (_, __) async {
          modelCalls++;
          throw StateError('prepared input must skip recognition');
        },
        send: (request) async {
          if (request.method == 'POST') {
            posts.add(request.body);
            return http.Response('{"id":"cloud"}', 200);
          }
          final cloud =
              ServerConversation(id: 'cloud', createdAt: DateTime.utc(2026), structured: Structured('Synthetic', ''));
          return http.Response(
              jsonEncode({...cloud.toJson(), 'transcript_segments': restored.onDevicePreparedUpload!['segments']}),
              200);
        });
    addTearDown(second.dispose);
    await second.run(transcribeNow: true);
    expect(modelCalls, 1);
    expect(posts, hasLength(4));
    expect(posts[0], posts[2]);
    expect(posts[1], posts[3]);
    expect(rows.single.transcriptSegments, hasLength(501));
    expect(restored.onDevicePreparedUpload, isNull);
    expect(controller.lastRunFailed, isFalse);
  });

  for (final retire in [false, true]) {
    test('prepared input must persist for its owner before any chunk sends (retire=$retire)', () async {
      await setRefactorFlags({'clients_from_segments_chunks': true});
      final audio = await recording(frames: 100);
      final wal = Wal(
          timerStart: 1700000000,
          codec: BleAudioCodec.pcm16,
          seconds: 1,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          filePath: 'synthetic.bin',
          onDeviceOnly: true);
      late LocalWalSyncImpl sync;
      sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {
        if (retire) {
          sync.clearUserData();
        } else {
          throw StateError('index unavailable');
        }
      })
        ..testWals = [wal];
      final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource())
        ..debugActivate();
      addTearDown(controller.dispose);
      var sends = 0;
      final runner = OnDeviceRunner(
          sync: sync,
          controller: controller,
          publish: (_) {},
          cloudBaseUrl: 'http://127.0.0.1:1/',
          transcribeChunk: (_, __) async => const OnDeviceBatchResult(
              engine: 'synthetic', text: 'synthetic', words: [OnDeviceWord('synthetic', 0, 1)]),
          send: (_) async {
            sends++;
            return http.Response('{"id":"cloud"}', 200);
          });
      addTearDown(runner.dispose);
      await runner.run(transcribeNow: true);
      expect(sends, 0);
      expect(wal.onDeviceConversation, isNull);
      if (!retire) expect(wal.onDevicePreparedUpload, isNull);
      expect(await audio.exists(), isTrue);
    });
  }

  test('local summaries survive refresh only with a bound digest and the feature on', () {
    final segments = [
      TranscriptSegment(
          id: '1',
          text: 'Synthetic speech.',
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          start: 0,
          end: 1,
          translations: const [],
          sttProvider: 'on_device:synthetic')
    ];
    final projection = {
      'transcript_sha256': onDeviceTranscriptHash(segments),
      'schema_version': 1,
      'action_items': [],
      'provenance': {
        'runtime': 'local',
        'device_class': 'iphone',
        'model_id': 'apple-foundation-models',
        'generated_at': '2026-10-14T00:00:00Z'
      },
      'structure': {'title': 'Local title', 'overview': 'Local overview'}
    };
    final row = ServerConversation(
        id: 'test',
        createdAt: DateTime.utc(2026),
        structured: Structured('Cloud title', ''),
        transcriptSegments: segments,
        clientProcessing: projection);
    expect(applyOnDeviceProjection(row, enabled: false), same(row));
    expect(applyOnDeviceProjection(row, enabled: true).structured.title, 'Local title');
    segments.first.text = 'Different speech.';
    expect(applyOnDeviceProjection(row, enabled: true), same(row));
  });

  test('v5 digest binds attribution and canonical UTF8 fields', () {
    TranscriptSegment segment(String text, {bool user = false}) => TranscriptSegment(
        id: '1',
        text: text,
        speaker: 'SPEAKER_00',
        isUser: user,
        personId: null,
        start: 0,
        end: 1,
        translations: const []);
    expect(onDeviceTranscriptHash([segment(' hello ')]), onDeviceTranscriptHash([segment('hello')]));
    expect(onDeviceTranscriptHash([segment('hello')]), isNot(onDeviceTranscriptHash([segment('hello', user: true)])));
    expect(onDeviceTranscriptHash([]), 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
  });
}
