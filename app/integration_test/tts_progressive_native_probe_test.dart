// ignore_for_file: experimental_member_use

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/services/voice_playback/progressive_tts_audio_source.dart';

const _assetPath = 'assets/test/tts_progressive_probe.mp3';
const _dripBytes = 4 * 1024;
const _dripInterval = Duration(milliseconds: 200);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('native decoder produces progressive PCM before a full-download client', (tester) async {
    final asset = await rootBundle.load(_assetPath);
    final mp3 = asset.buffer.asUint8List(asset.offsetInBytes, asset.lengthInBytes);
    final server = await _SlowMp3Server.start(mp3);
    addTearDown(server.close);

    // ignore: avoid_print
    print('NATIVE_TTS_PROBE phase=materialized_start');
    final oldMs = await _measureMaterialized(server.uri);
    // ignore: avoid_print
    print('NATIVE_TTS_PROBE phase=materialized_done old_ms=$oldMs');
    final progressiveMs = await _measureProgressive(server.uri);

    // Kept machine-readable so the PR can report an exact, repeatable result.
    // ignore: avoid_print
    print(
      'NATIVE_TTS_PROBE platform=${Platform.operatingSystem} bytes=${mp3.length} '
      'drip_bytes=$_dripBytes drip_ms=${_dripInterval.inMilliseconds} '
      'old_ms=$oldMs progressive_ms=$progressiveMs',
    );
    expect(progressiveMs, lessThan(oldMs));
  }, timeout: const Timeout(Duration(minutes: 2)));
}

Future<int> _measureMaterialized(Uri uri) async {
  final stopwatch = Stopwatch()..start();
  final client = HttpClient();
  final request = await client.getUrl(uri);
  final response = await request.close();
  final builder = BytesBuilder(copy: false);
  await for (final bytes in response) {
    builder.add(bytes);
  }
  client.close();
  // The old path cannot hand anything to its native player before this full
  // materialization point. This is therefore a conservative lower bound for
  // its time-to-first-audio, without mixing decoder startup into the baseline.
  builder.takeBytes();
  return stopwatch.elapsedMilliseconds;
}

Future<int> _measureProgressive(Uri uri) async {
  final stopwatch = Stopwatch()..start();
  final client = HttpClient();
  final request = await client.getUrl(uri);
  final response = await request.close();
  final compressed = BytesBuilder(copy: false);
  try {
    await for (final bytes in response) {
      compressed.add(bytes);
      if (compressed.length < progressiveTtsPrebufferBytes) continue;
      try {
        final decoded = await const MethodChannel('com.omi/tts_mp3_decoder')
            .invokeMapMethod<String, dynamic>('decode', {'bytes': compressed.toBytes()});
        final pcm = decoded?['pcm'];
        if (pcm is Uint8List && pcm.isNotEmpty) {
          // ignore: avoid_print
          print(
            'NATIVE_TTS_PROBE phase=pcm_ready elapsed_ms=${stopwatch.elapsedMilliseconds} '
            'channels=${decoded?['channels']} sample_rate=${decoded?['sample_rate']} pcm_bytes=${pcm.length}',
          );
          return stopwatch.elapsedMilliseconds;
        }
      } on PlatformException {
        // A partial MP3 frame may straddle this HTTP increment. The production
        // player retries after another bounded increment in the same way.
      }
    }
    throw StateError('Native decoder produced no PCM');
  } finally {
    client.close(force: true);
  }
}

class _SlowMp3Server {
  final HttpServer _server;
  final StreamSubscription<HttpRequest> _requests;

  _SlowMp3Server._(this._server, this._requests);

  Uri get uri => Uri.parse('http://127.0.0.1:${_server.port}/probe.mp3');

  static Future<_SlowMp3Server> start(Uint8List mp3) async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    late final StreamSubscription<HttpRequest> requests;
    requests = server.listen((request) async {
      request.response.headers.contentType = ContentType('audio', 'mpeg');
      // No content-length: force the same chunked HTTP semantics as the new
      // backend rather than letting the native player infer a complete file.
      try {
        for (var offset = 0; offset < mp3.length; offset += _dripBytes) {
          final end = (offset + _dripBytes).clamp(0, mp3.length);
          request.response.add(mp3.sublist(offset, end));
          await request.response.flush();
          if (end < mp3.length) await Future<void>.delayed(_dripInterval);
        }
      } on SocketException {
        // The progressive measurement stops as soon as playback advances.
      } finally {
        await request.response.close();
      }
    });
    return _SlowMp3Server._(server, requests);
  }

  Future<void> close() async {
    await _requests.cancel();
    await _server.close(force: true);
  }
}
