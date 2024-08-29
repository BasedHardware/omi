import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/logic/websocket_mixin.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/websockets.dart';

class SpeechProfileProvider extends ChangeNotifier with MessageNotifierMixin, WebSocketMixin {
  DeviceProvider? deviceProvider;
  CaptureProvider? captureProvider;
  bool? permissionEnabled;
  bool loading = false;
  BTDeviceStruct? device;

  final targetWordsCount = 70;
  final maxDuration = 90;
  StreamSubscription<OnConnectionStateChangedEvent>? connectionStateListener;
  List<TranscriptSegment> segments = [];
  double? streamStartedAtSecond;
  WavBytesUtil audioStorage = WavBytesUtil(codec: BleAudioCodec.opus);
  StreamSubscription? _bleBytesStream;

  bool startedRecording = false;
  double percentageCompleted = 0;
  bool uploadingProfile = false;
  bool profileCompleted = false;
  Timer? forceCompletionTimer;

  String text = '';
  String message = '';

  void setProvider(DeviceProvider provider, CaptureProvider captureProvider) {
    deviceProvider = provider;
    this.captureProvider = captureProvider;
    notifyListeners();
  }

  initialise() async {
    device = deviceProvider?.connectedDevice;
    device ??= await deviceProvider?.scanAndConnectToDevice();
    captureProvider?.resetState(restartBytesProcessing: false);
    initiateWebsocket();
    if (device != null) initiateFriendAudioStreaming();
    // initiateConnectionListener();
    notifyListeners();
  }

  void updateStartedRecording(bool value) {
    startedRecording = value;
    notifyListeners();
  }

  changeLoadingState() {
    loading = !loading;
    notifyListeners();
  }

  initiateConnectionListener() async {
    if (device == null || connectionStateListener != null) return;
    connectionStateListener = getConnectionStateListener(
        deviceId: device!.id,
        onDisconnected: () {
          device = null;
          notifyListeners();
        },
        onConnected: ((d) {
          device = d;
          notifyListeners();
          initiateFriendAudioStreaming();
        }));
  }

  Future<void> initiateWebsocket() async {
    await initWebSocket(
      codec: BleAudioCodec.opus,
      sampleRate: 16000,
      includeSpeechProfile: false,
      onConnectionSuccess: () {
        notifyListeners();
      },
      onConnectionFailed: (err) {
        notifyError('WS_ERR');
      },
      onConnectionClosed: (int? closeCode, String? closeReason) {},
      onConnectionError: (err) {
        notifyError('WS_ERR');
      },
      onMessageReceived: (List<TranscriptSegment> newSegments) {
        if (newSegments.isEmpty) return;
        if (segments.isEmpty) {
          audioStorage.removeFramesRange(fromSecond: 0, toSecond: newSegments[0].start.toInt());
        }
        streamStartedAtSecond ??= newSegments[0].start;

        TranscriptSegment.combineSegments(
          segments,
          newSegments,
          toRemoveSeconds: streamStartedAtSecond ?? 0,
        );
        updateProgressMessage();
        _validateSingleSpeaker();
        _handleCompletion();
        notifyInfo('SCROLL_DOWN');
        debugPrint('Memory creation timer restarted');
      },
    );
  }

  _handleCompletion() async {
    if (uploadingProfile || profileCompleted) return;
    String text = segments.map((e) => e.text).join(' ').trim();
    int wordsCount = text.split(' ').length;
    percentageCompleted = (wordsCount / targetWordsCount).clamp(0, 1);
    notifyListeners();
    if (percentageCompleted == 1) finalize();
    notifyListeners();
  }

  finalize() async {
    if (uploadingProfile || profileCompleted) return;

    int duration = segments.isEmpty ? 0 : segments.last.end.toInt();
    if (duration < 5 || duration > 120) {
      notifyError('INVALID_RECORDING');
    }

    String text = segments.map((e) => e.text).join(' ').trim();
    if (text.split(' ').length < (targetWordsCount / 2)) {
      // 25 words
      notifyError('TOO_SHORT');
    }
    uploadingProfile = true;
    notifyListeners();
    closeWebSocket();
    forceCompletionTimer?.cancel();
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();

    List<List<int>> raw = List.from(audioStorage.rawPackets);
    var data = await audioStorage.createWavFile(filename: 'speaker_profile.wav');
    await uploadProfile(data.item1);
    await uploadProfileBytes(raw, duration);

    SharedPreferencesUtil().hasSpeakerProfile = true;

    uploadingProfile = false;
    profileCompleted = true;
    notifyListeners();
  }

  Future<void> initiateFriendAudioStreaming() async {
    _bleBytesStream = await getBleAudioBytesListener(
      device!.id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;
        audioStorage.storeFramePacket(value);
        value.removeRange(0, 3);
        if (wsConnectionState == WebsocketConnectionStatus.connected) {
          websocketChannel?.sink.add(value);
        }
      },
    );
  }

  _validateSingleSpeaker() {
    int speakersCount = segments.map((e) => e.speaker).toSet().length;
    debugPrint('_validateSingleSpeaker speakers count: $speakersCount');
    if (speakersCount > 1) {
      var speakerToWords = segments.fold<Map<int, int>>(
        {},
        (previousValue, element) {
          previousValue[element.speakerId] = (previousValue[element.speakerId] ?? 0) + element.text.split(' ').length;
          return previousValue;
        },
      );
      debugPrint('speakerToWords: $speakerToWords');
      if (speakerToWords.values.every((element) => element / segments.length > 0.2)) {
        notifyError('MULTIPLE_SPEAKERS');
      }
    }
  }

  void resetSegments() {
    segments.clear();
    streamStartedAtSecond = null;
    audioStorage.clearAudioBytes();
    notifyListeners();
  }

  Future setupSpeechRecording() async {
    final permission = await getStoreRecordingPermission();
    permissionEnabled = permission;
    if (permission != null) {
      SharedPreferencesUtil().permissionStoreRecordingsEnabled = permission;
    }
    notifyListeners();
  }

  void updateProgressMessage() {
    text = segments.map((e) => e.text).join(' ').trim();
    int wordsCount = text.split(' ').length;
    message = 'Keep speaking until you get 100%.';
    if (wordsCount > 10) {
      message = 'Keep going, you are doing great';
    } else if (wordsCount > 25) {
      message = 'Great job, you are almost there';
    } else if (wordsCount > 40) {
      message = 'So close, just a little more';
    }
    notifyListeners();
  }

  void close() {
    print('Closing speech profile provider');
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
    forceCompletionTimer?.cancel();
    segments.clear();
    // captureProvider?.resetState(restartBytesProcessing: true);
    closeWebSocket();
  }

  @override
  void dispose() {
    // This won't be called unless the provider is removed from the widget tree. So we need to manually call this in the widget's dispose method.
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
    forceCompletionTimer?.cancel();
    super.dispose();
  }
}
