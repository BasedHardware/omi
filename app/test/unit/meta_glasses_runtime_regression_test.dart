import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

String _functionBody(String source, String functionName) {
  final start = source.indexOf(functionName);
  if (start < 0) {
    fail('Missing function $functionName');
  }

  final open = source.indexOf('{', start);
  if (open < 0) {
    fail('Missing opening brace for $functionName');
  }

  var depth = 0;
  for (var i = open; i < source.length; i++) {
    final char = source.codeUnitAt(i);
    if (char == 123) depth++;
    if (char == 125) depth--;
    if (depth == 0) return source.substring(open, i + 1);
  }

  fail('Missing closing brace for $functionName');
}

String _asyncMethodBody(String source, String functionName) {
  final start = source.indexOf(functionName);
  if (start < 0) {
    fail('Missing function $functionName');
  }

  final asyncOpen = source.indexOf(') async {', start);
  if (asyncOpen < 0) {
    fail('Missing async opening brace for $functionName');
  }

  final open = source.indexOf('{', asyncOpen);
  var depth = 0;
  for (var i = open; i < source.length; i++) {
    final char = source.codeUnitAt(i);
    if (char == 123) depth++;
    if (char == 125) depth--;
    if (depth == 0) return source.substring(open, i + 1);
  }

  fail('Missing closing brace for $functionName');
}

String _getterExpression(String source, String getterName) {
  final start = source.indexOf(getterName);
  if (start < 0) {
    fail('Missing getter $getterName');
  }

  final end = source.indexOf(';', start);
  if (end < 0) {
    fail('Missing getter terminator for $getterName');
  }

  return source.substring(start, end + 1);
}

void main() {
  group('Meta glasses runtime regressions', () {
    test('vendored DAT plugin records auditable upstream provenance', () {
      final provenance = _read('third_party/meta_wearables_dat_flutter/UPSTREAM.md');

      expect(provenance, contains('f13cf7e2bfbbc25bdbd42ca4972be1834c724624'));
      expect(provenance, contains('15 modified files'));
      expect(provenance, contains('Why vendored'));
    });

    test('Meta photo ingestion uses only the deployed websocket transport', () {
      final conversationsApi = _read('lib/backend/http/api/conversations.dart');
      final controller = _read('lib/services/capture/capture_controller.dart');

      expect(conversationsApi, isNot(contains('v1/meta-wearables/photos/cache')));
      expect(conversationsApi, isNot(contains('cacheMetaWearablesPhoto')));
      expect(controller, isNot(contains('cacheCapturedImage')));
      expect(controller, contains("'type': 'image_chunk'"));
    });

    test('background camera capture does not use shuttered still-photo loop', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final automaticLoop = _functionBody(provider, '_startPhotoLoop');

      // Background capture is driven by the native-pushed videoFramesStream
      // (keeps firing while backgrounded), not a Dart Timer (which suspends).
      // Shutter-free: continuous session, no per-frame pause/resume, no
      // hardware still capture.
      expect(provider, contains('videoFramesStream'),
          reason: 'background capture must subscribe to the DAT video frames (works backgrounded)');
      expect(provider, contains('_service.videoFrames().listen'),
          reason: 'the frame stream is the background-capable capture trigger');
      expect(provider, isNot(contains('Timer.periodic(_photoInterval')),
          reason: 'a Dart timer is suspended in the background; use the native frame stream instead');
      expect(provider, isNot(contains('_pausePreviewBetweenFrames')),
          reason: 'per-frame pause/resume produced the shutter/snapshot cadence and must be gone');
      expect(automaticLoop, isNot(contains('capturePhoto')),
          reason: 'automatic background capture must not trigger the glasses still-photo shutter');
      expect(automaticLoop, isNot(contains('takePicture')),
          reason: 'automatic background capture must not call any hardware still capture API');
    });

    test('video streaming errors are caught and moved to recoverable state', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');

      expect(provider, contains('videoStreamingError'));
      expect(provider, contains('MetaGlassStreamDiag'));
      expect(provider, contains('recoverFromVideoStreamingError'));
      expect(provider, contains('streamFailureCount'));
      expect(provider, contains('micOnlyFallback'));
    });

    test('runtime proof events persist in the app container when device logs are unavailable', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');

      expect(provider, contains('meta_glasses_runtime_proof.log'));
      expect(provider, contains('_runtimeProofLogFile'));
      expect(provider, contains('_runtimeProofLogMaxBytes'));
      expect(provider, contains('_appendRuntimeProof'));
      expect(provider, contains('MetaGlassStreamDiag stream-started'));
      expect(provider, contains('MetaGlassStreamDiag frame-event'));
      expect(provider, contains('MetaGlassStreamDiag camera-unavailable'));
      expect(provider, contains('gestures=media-remote'));
      expect(provider, contains('writeAsStringSync'));
    });

    test('runtime proof log explains why auto capture did not start', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');

      expect(provider, contains('MetaGlassRuntimeProof registration-state'));
      expect(provider, contains('MetaGlassRuntimeProof devices count='));
      expect(provider, contains('MetaGlassRuntimeProof active-device'));
      expect(provider, contains('MetaGlassRuntimeProof auto-start-skip'));
      expect(provider, contains('MetaGlassRuntimeProof auto-starting'));
    });

    test('runtime proof log reports capture mode and camera stream gates', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');

      expect(provider, contains('MetaGlassRuntimeProof start-capture'));
      expect(provider, contains('MetaGlassStreamDiag start-photo-loop'));
      expect(provider, contains('cameraPermission='));
      expect(provider, contains('captureMode='));
    });

    test('photo queue waits for server-side cache ack before deleting local frames', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final controller = _read('lib/services/capture/capture_controller.dart');
      final flushPhotoQueue = _functionBody(provider, 'Future<void> flushPhotoQueue');
      final ingestCapturedImage = _asyncMethodBody(controller, 'Future<bool> ingestCapturedImage');
      final eventHandler = _functionBody(controller, 'void onMessageEventReceived');

      expect(flushPhotoQueue, contains('if (!sent)'));
      expect(flushPhotoQueue, contains("lastUploadStatus: 'upload_failed'"));
      expect(flushPhotoQueue, contains('break;'));
      expect(controller, contains('_pendingPhotoUploadAcks'));
      expect(controller, contains('_pendingPhotoUploadIdsByPermanent'));
      expect(ingestCapturedImage, contains('_waitForPhotoUploadAck'));
      expect(eventHandler, contains('PhotoProcessingEvent'));
      expect(eventHandler, contains('_completePhotoUploadAck'));
    });

    test('glasses capture never falls back to the iPhone mic while mixing media playback', () {
      // The REST photo-cache endpoint (v1/meta-wearables/photos/cache) exists
      // only in the local repo backend — api.omi.me returns 404 for it, so
      // every REST upload fails and photos never reach history (observed
      // 2026-07-05: 4 frames stuck in the sync queue). The only ingestion
      // path deployed on prod is the transcription socket: image_chunk
      // messages for photos and PCM16 audio for STT. Meta DAT does not expose
      // microphone frames, so Omi must require the paired glasses' HFP input
      // and must never silently fall back to the built-in iPhone microphone.
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final controller = _read('lib/services/capture/capture_controller.dart');
      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      final backgroundStreaming = _read(
        'third_party/meta_wearables_dat_flutter/ios/meta_wearables_dat_flutter/Sources/'
        'meta_wearables_dat_flutter/BackgroundStreamingController.swift',
      );
      final glassesAudioSession = _functionBody(appDelegate, 'private func configureMetaGlassesCaptureSession');
      final startCapture = _asyncMethodBody(provider, 'Future<bool> startCapture');
      final stopCapture = _asyncMethodBody(provider, 'Future<void> stopCapture');
      final flushPhotoQueue = _functionBody(provider, 'Future<void> flushPhotoQueue');

      expect(startCapture, contains('configureForMetaGlassesCapture'));
      expect(startCapture, contains('getCurrentAudioRoute'));
      expect(startCapture, contains("route?['glassesInput']"));
      expect(startCapture, contains("route?['input']"));
      expect(startCapture, contains("route?['output']"));
      expect(startCapture, contains(r'audio-stream-started input=$input output=$output'));
      expect(startCapture, isNot(contains('configureForBluetooth')));
      expect(startCapture.indexOf('configureForMetaGlassesCapture'), lessThan(startCapture.indexOf('streamRecording')));
      expect(startCapture.indexOf('streamRecording'), lessThan(startCapture.indexOf('_startPhotoLoop')),
          reason: 'Meta requires HFP audio to settle before the DAT camera stream starts.');
      expect(startCapture, contains('stopStreamRecording'));
      expect(provider, contains("call.method == 'onAudioRouteChanged'"));
      expect(provider, contains('audio-route-lost'));
      for (final nativeSource in [glassesAudioSession, backgroundStreaming]) {
        expect(nativeSource, contains('.mixWithOthers'));
        expect(nativeSource, contains('.allowBluetoothHFP'));
        expect(nativeSource, contains('.bluetoothHFP'));
        expect(nativeSource, contains('mode: .videoRecording'));
        expect(nativeSource, contains('setPreferredInput'));
        expect(nativeSource, isNot(contains('.builtInMic')));
      }
      expect(glassesAudioSession, contains('glassesMicrophoneUnavailable'));
      expect(glassesAudioSession, contains('currentAudioRoute()'));
      expect(appDelegate, contains('AVAudioSession.sharedInstance().currentRoute'));
      expect(appDelegate, contains('AVAudioSession.Port'));
      expect(glassesAudioSession, isNot(contains('.defaultToSpeaker')));
      expect(appDelegate, contains('call.method == "configureForBluetooth"'),
          reason: 'non-Meta voice-recorder flows still use the legacy Bluetooth route');
      expect(startCapture, contains('streamRecording'),
          reason: 'the transcription socket is the only prod transport for photos + audio');
      expect(stopCapture, contains('stopStreamRecording'), reason: 'capture stop must close the audio stream');
      expect(flushPhotoQueue, contains('_cachePhotoBytes'));
      expect(provider, contains('ingestCapturedImage'),
          reason: 'photos go out as image_chunk socket messages, the path prod actually accepts');
      expect(provider, isNot(contains('cacheCapturedImage')),
          reason: 'REST photo cache is not deployed on api.omi.me; uploads 404 and strand the queue');
      expect(controller, contains('Future<bool> ingestCapturedImage'));
    });

    test('meta capture only enters capturing state after camera stream is live', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final startCapture = _asyncMethodBody(provider, 'Future<bool> startCapture');

      expect(provider, contains('_cameraCaptureStreamReady'));
      expect(provider, contains('_firstQueuedFrameCompleter'));
      expect(provider, contains('_streamGeneration'));
      expect(provider, contains('final generation = _streamGeneration'));
      expect(provider, contains('generation != _streamGeneration'));
      expect(provider, contains('_waitForFirstQueuedFrame'));
      expect(startCapture.indexOf('_waitForFirstQueuedFrame'), lessThan(startCapture.indexOf('isCapturing = true')));
      expect(startCapture.indexOf('_cameraCaptureStreamReady'), lessThan(startCapture.indexOf('isCapturing = true')));
      expect(startCapture, contains('MetaWearablesDat.disableBackgroundStreaming'));
      expect(startCapture, contains('return false'));
    });

    test('meta capture recovery does not leave dead camera as active capture', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final recover = _asyncMethodBody(provider, 'Future<void> recoverFromVideoStreamingError');
      final captureFrame = _asyncMethodBody(provider, 'Future<void> _captureFrame');
      final autoStart = _asyncMethodBody(provider, 'Future<void> _maybeAutoStartCapture');
      final setCaptureInterval = _asyncMethodBody(provider, 'Future<void> setCaptureInterval');

      expect(recover, contains('isCapturing = false'));
      expect(recover, contains('MetaWearablesDat.disableBackgroundStreaming'));
      expect(captureFrame, contains('unawaited(flushPhotoQueue())'));
      expect(captureFrame, isNot(contains('await flushPhotoQueue()')));
      expect(autoStart, contains('final started = await startCapture(controller)'));
      expect(autoStart, contains('auto-start-failed'));
      expect(autoStart, contains('_scheduleAutoStartRetry()'));
      expect(provider, contains('void _scheduleAutoStartRetry()'));
      expect(provider, contains('_cancelAutoStartRetry()'));
      expect(setCaptureInterval, contains('_evaluateCaptureWatchdog()'));
    });

    test('not-ready polling remains reachable for paired but disconnected devices', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final hasCandidate = _getterExpression(provider, 'bool get _hasSessionCandidateDevice');
      final shouldPoll = _getterExpression(provider, 'bool get _shouldPollNotReady');

      expect(hasCandidate, isNot(contains('devices.isNotEmpty')));
      expect(shouldPoll, contains('devices.isNotEmpty'));
      expect(shouldPoll, contains('!_hasSessionCandidateDevice'));
      expect(shouldPoll.indexOf('devices.isNotEmpty'), lessThan(shouldPoll.indexOf('!_hasSessionCandidateDevice')));
    });

    test('video frame listener drops events from stale stream generations', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final onVideoFrame = _functionBody(provider, 'void _onVideoFrame');

      expect(provider, contains('final listenerGeneration = _streamGeneration'));
      expect(provider, contains('_onVideoFrame(frame, listenerGeneration)'));
      expect(provider, contains('void _onVideoFrame(VideoFrame frame, int listenerGeneration)'));
      expect(onVideoFrame, contains('listenerGeneration != _streamGeneration'));
      expect(onVideoFrame.indexOf('listenerGeneration != _streamGeneration'),
          lessThan(onVideoFrame.indexOf('_lastFrameForwardedAt = now')));
      expect(onVideoFrame, contains('frame-event-stale'));
    });

    test('retry exhaustion schedules connected auto-start recovery', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final recover = _asyncMethodBody(provider, 'Future<void> recoverFromVideoStreamingError');

      expect(recover, contains('_scheduleAutoStartRetry()'));
      expect(recover.indexOf('_scheduleAutoStartRetry()'), greaterThan(recover.indexOf('isCapturing = false')));
      expect(recover, contains('recover-exhausted-autostart-retry'));
      expect(recover, contains('_scheduleNotReadyRefresh()'));
    });

    test('frame in-flight guard belongs to the generation that set it', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final captureFrame = _asyncMethodBody(provider, 'Future<void> _captureFrame');

      expect(provider, contains('int? _frameForwardInFlightGeneration'));
      expect(captureFrame, contains('_frameForwardInFlightGeneration = generation'));
      expect(captureFrame, contains('_frameForwardInFlightGeneration == generation'));
      expect(captureFrame, contains('_frameForwardInFlightGeneration = null'));
      expect(captureFrame.indexOf('_frameForwardInFlightGeneration == generation'),
          lessThan(captureFrame.indexOf('_frameForwardInFlight = false')));
    });

    test('glasses tap gestures ride the media-remote bridge while capture holds the audio session', () {
      // The DAT SDK has no gesture API. Stalk taps arrive as Bluetooth AVRCP
      // media commands, which iOS only delivers to the current Now Playing
      // app with an active audio session — capture provides both. The bridge
      // is instrumented end to end (OmiMetaGestures native logs,
      // MetaGlassGestureDiag Dart proof events) so hardware runs show
      // whether events actually arrive instead of silently claiming support.
      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('com.omi/meta_gestures'));
      expect(appDelegate, contains('OmiMetaGestures'));
      expect(appDelegate, contains('MPRemoteCommandCenter.shared()'));
      expect(appDelegate, contains('removeTarget(nil)'), reason: 'remote command targets must not double-register');
      expect(appDelegate, contains('togglePlayPauseCommand'));
      expect(appDelegate, contains('nextTrackCommand'));
      expect(appDelegate, contains('invokeMethod("onGesture"'));
      expect(appDelegate, contains('MPNowPlayingInfoCenter.default().playbackState = .playing'));
      expect(appDelegate, contains('MPNowPlayingInfoCenter.default().playbackState = .stopped'));

      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final startCapture = _asyncMethodBody(provider, 'Future<bool> startCapture');
      final stopCapture = _asyncMethodBody(provider, 'Future<void> stopCapture');
      expect(provider, contains("MethodChannel('com.omi/meta_gestures')"));
      expect(startCapture, contains('_startGestureListening'),
          reason: 'gesture delivery needs the capture audio session; start them together');
      expect(stopCapture, contains('_stopGestureListening'));
      expect(provider, contains('MetaGlassGestureDiag listening-started'));
      expect(provider, contains('MetaGlassGestureDiag received'));
      expect(provider, contains('_gestureDebounce'),
          reason: 'one physical tap can double-fire play + togglePlayPause; collapse duplicates');
      expect(provider, contains('_gestureActivationGrace'),
          reason: 'claiming the BT route fires a phantom AVRCP pause ~400ms after listening starts '
              '(observed on-device 2026-07-05 15:34:36); it must not toggle capture off');
      expect(provider, contains('phantom'),
          reason: 'the grace-window discard must be logged so hardware runs can tell phantom from real taps');
    });

    test('meta capture diagnostics expose relay health fields', () {
      final source = _read('lib/services/meta_wearables/meta_capture_diagnostics.dart');
      final provider = _read('lib/providers/meta_wearables_provider.dart');

      expect(source, contains('lastFrameAt'));
      expect(source, contains('pendingQueueCount'));
      expect(source, contains('lastUploadStatus'));
      expect(source, contains('streamState'));
      expect(source, contains('sessionState'));
      expect(source, contains('failedUploadCount'));
      expect(provider, contains("'enqueue_failed'"));
      expect(provider, contains('_lastDiagnosticsLogAt'));
      expect(provider, contains('const Duration(seconds: 5)'));
      expect(provider, contains('Meta capture diagnostics:'));
    });
  });
}
