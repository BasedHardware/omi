import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/message_event.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/services/sockets/pure_socket.dart';
import 'package:friend_private/services/sockets/sdcard_socket.dart';
import 'package:friend_private/services/sockets/transcription_connection.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';

class CaptureProvider extends ChangeNotifier
    with MessageNotifierMixin
    implements ITransctipSegmentSocketServiceListener {
  MemoryProvider? memoryProvider;
  MessageProvider? messageProvider;
  TranscriptSegmentSocketService? _socket;
  SdCardSocketService sdCardSocket = SdCardSocketService();
  Timer? _keepAliveTimer;

  // In progress memory
  ServerMemory? _inProgressMemory;

  ServerMemory? get inProgressMemory => _inProgressMemory;

  IWalService get _wal => ServiceManager.instance().wal;

  IDeviceService get _deviceService => ServiceManager.instance().device;
  bool _isWalSupported = false;

  bool get isWalSupported => _isWalSupported;

  StreamSubscription<InternetStatus>? _internetStatusListener;
  InternetStatus? _internetStatus;

  get internetStatus => _internetStatus;

  CaptureProvider() {
    _internetStatusListener = PureCore().internetConnection.onStatusChange.listen((InternetStatus status) {
      onInternetSatusChanged(status);
    });
  }

  void updateProviderInstances(MemoryProvider? mp, MessageProvider? p) {
    memoryProvider = mp;
    messageProvider = p;
    notifyListeners();
  }

  BtDevice? _recordingDevice;
  List<TranscriptSegment> segments = [];

  bool hasTranscripts = false;

  StreamSubscription? _bleBytesStream;

  get bleBytesStream => _bleBytesStream;

  StreamSubscription? _storageStream;

  get storageStream => _storageStream;

  RecordingState recordingState = RecordingState.stop;

  bool _transcriptServiceReady = false;

  bool get transcriptServiceReady => _transcriptServiceReady && _internetStatus == InternetStatus.connected;

  bool get recordingDeviceServiceReady => _recordingDevice != null || recordingState == RecordingState.record;

  // -----------------------
  // Memory creation variables
  String conversationId = const Uuid().v4();

  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setMemoryCreating(bool value) {
    debugPrint('set memory creating $value');
    // memoryCreating = value;
    notifyListeners();
  }

  void _updateRecordingDevice(BtDevice? device) {
    debugPrint('connected device changed from ${_recordingDevice?.id} to ${device?.id}');
    _recordingDevice = device;
    notifyListeners();
  }

  void updateRecordingDevice(BtDevice? device) {
    _updateRecordingDevice(device);
  }

  Future _resetStateVariables() async {
    segments = [];
    conversationId = const Uuid().v4();
    hasTranscripts = false;
    notifyListeners();
  }

  Future<void> onRecordProfileSettingChanged() async {
    await _resetState();
  }

  Future<void> changeAudioRecordProfile([
    BleAudioCodec? audioCodec,
    int? sampleRate,
  ]) async {
    debugPrint("changeAudioRecordProfile");
    await _resetState();
    await _initiateWebsocket(audioCodec: audioCodec, sampleRate: sampleRate);
  }

  Future<void> _initiateWebsocket({
    BleAudioCodec? audioCodec,
    int? sampleRate,
    bool force = false,
  }) async {
    debugPrint('initiateWebsocket in capture_provider');

    BleAudioCodec codec = audioCodec ?? SharedPreferencesUtil().deviceCodec;
    sampleRate ??= (codec == BleAudioCodec.opus ? 16000 : 8000);

    debugPrint('is ws null: ${_socket == null}');

    // Connect to the transcript socket
    String language = SharedPreferencesUtil().recordingsLanguage;
    _socket = await ServiceManager.instance()
        .socket
        .memory(codec: codec, sampleRate: sampleRate, language: language, force: force);
    if (_socket == null) {
      _startKeepAliveServices();
      debugPrint("Can not create new memory socket");
      return;
    }
    _socket?.subscribe(this, this);
    _transcriptServiceReady = true;

    _loadInProgressMemory();

    notifyListeners();
  }

  Future streamAudioToWs(String id, BleAudioCodec codec) async {
    debugPrint('streamAudioToWs in capture_provider');
    _bleBytesStream?.cancel();
    _bleBytesStream = await _getBleAudioBytesListener(id, onAudioBytesReceived: (List<int> value) {
      if (value.isEmpty) return;

      // support: opus codec, 1m from the first device connectes
      var deviceFirstConnectedAt = _deviceService.getFirstConnectedAt();
      var checkWalSupported = codec == BleAudioCodec.opus &&
          (deviceFirstConnectedAt != null &&
              deviceFirstConnectedAt.isBefore(DateTime.now().subtract(const Duration(seconds: 15)))) &&
          SharedPreferencesUtil().localSyncEnabled;
      if (checkWalSupported != _isWalSupported) {
        setIsWalSupported(checkWalSupported);
      }
      if (_isWalSupported) {
        _wal.getSyncs().phone.onByteStream(value);
      }

      // send ws
      if (_socket?.state == SocketServiceState.connected) {
        final trimmedValue = value.sublist(3);
        _socket?.send(trimmedValue);

        // synced
        if (_isWalSupported) {
          _wal.getSyncs().phone.onBytesSync(value);
        }
      }
    });
    notifyListeners();
  }

  Future<void> _resetState() async {
    debugPrint('resetState');
    _cleanupCurrentState();
    await _recheckCodecChange();
    await _ensureSocketConnection();
    await _initiateFriendAudioStreaming();
    await initiateStorageBytesStreaming(); // ??
    notifyListeners();
  }

  void _cleanupCurrentState() {
    closeBleStream();
    cancelMemoryCreationTimer();
  }

  // TODO: use connection directly
  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
  }

  Future<StreamSubscription?> _getBleStorageBytesListener(
    String deviceId, {
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleStorageBytesListener(onStorageBytesReceived: onStorageBytesReceived);
  }

  Future<StreamSubscription?> _getBleAudioBytesListener(
    String deviceId, {
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleAudioBytesListener(onAudioBytesReceived: onAudioBytesReceived);
  }

  Future<bool> _recheckCodecChange() async {
    if (_recordingDevice != null) {
      BleAudioCodec newCodec = await _getAudioCodec(_recordingDevice!.id);
      if (SharedPreferencesUtil().deviceCodec != newCodec) {
        debugPrint('Device codec changed from ${SharedPreferencesUtil().deviceCodec} to $newCodec');
        await SharedPreferencesUtil().setDeviceCodec(newCodec);
        return true;
      }
    }
    return false;
  }

  Future<void> _ensureSocketConnection() async {
    var codec = SharedPreferencesUtil().deviceCodec;
    var language = SharedPreferencesUtil().recordingsLanguage;
    if (language != _socket?.language || codec != _socket?.codec || _socket?.state != SocketServiceState.connected) {
      await _initiateWebsocket(audioCodec: codec, force: true);
    }
  }

  Future<void> _initiateFriendAudioStreaming() async {
    if (_recordingDevice == null) return;

    BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
    if (SharedPreferencesUtil().deviceCodec != codec) {
      debugPrint('Device codec changed from ${SharedPreferencesUtil().deviceCodec} to $codec');
      SharedPreferencesUtil().deviceCodec = codec;
      notifyInfo('FIM_CHANGE');
      await _ensureSocketConnection();
    }

    // Why is the _recordingDevice null at this point?
    if (_recordingDevice != null) {
      await streamAudioToWs(_recordingDevice!.id, codec);
    } else {
      // Is the app in foreground when this happens?
      Logger.handle(Exception('Device Not Connected'), StackTrace.current,
          message: 'Device Not Connected. Please make sure the device is turned on and nearby.');
    }

    notifyListeners();
  }

  void clearTranscripts() {
    segments = [];
    hasTranscripts = false;
    notifyListeners();
  }

  void closeBleStream() {
    _bleBytesStream?.cancel();
    notifyListeners();
  }

  void cancelMemoryCreationTimer() {
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBytesStream?.cancel();
    _socket?.unsubscribe(this);
    _keepAliveTimer?.cancel();
    _internetStatusListener?.cancel();
    super.dispose();
  }

  void updateRecordingState(RecordingState state) {
    recordingState = state;
    notifyListeners();
  }

  streamRecording() async {
    await Permission.microphone.request();

    // prepare
    await changeAudioRecordProfile(BleAudioCodec.pcm16, 16000);

    // record
    await ServiceManager.instance().mic.start(onByteReceived: (bytes) {
      if (_socket?.state == SocketServiceState.connected) {
        _socket?.send(bytes);
      }
    }, onRecording: () {
      updateRecordingState(RecordingState.record);
    }, onStop: () {
      updateRecordingState(RecordingState.stop);
    }, onInitializing: () {
      updateRecordingState(RecordingState.initialising);
    });
  }

  stopStreamRecording() async {
    _cleanupCurrentState();
    ServiceManager.instance().mic.stop();
    await _socket?.stop(reason: 'stop stream recording');
  }

  Future streamDeviceRecording({BtDevice? device}) async {
    debugPrint("streamDeviceRecording $device");
    if (device != null) _updateRecordingDevice(device);
    await _resetState();
  }

  Future stopStreamDeviceRecording({bool cleanDevice = false}) async {
    if (cleanDevice) {
      _updateRecordingDevice(null);
    }
    _cleanupCurrentState();
    await _socket?.stop(reason: 'stop stream device recording');
  }

  // Socket handling

  @override
  void onClosed() {
    _transcriptServiceReady = false;
    debugPrint('[Provider] Socket is closed');

    // Wait for in process memory or reset
    if (inProgressMemory == null) {
      _resetStateVariables();
    }

    notifyListeners();
    _startKeepAliveServices();
  }

  void _startKeepAliveServices() {
    if (_recordingDevice != null && _socket?.state != SocketServiceState.connected) {
      _keepAliveTimer?.cancel();
      _keepAliveTimer = Timer.periodic(const Duration(seconds: 15), (t) async {
        debugPrint("[Provider] keep alive...");

        if (_recordingDevice == null || _socket?.state == SocketServiceState.connected) {
          t.cancel();
          return;
        }

        await _initiateWebsocket();
      });
    }
  }

  @override
  void onError(Object err) {
    _transcriptServiceReady = false;
    debugPrint('err: $err');
    notifyListeners();
    _startKeepAliveServices();
  }

  @override
  void onConnected() {
    _transcriptServiceReady = true;
    notifyListeners();
  }

  void _loadInProgressMemory() async {
    var memories = await getMemories(statuses: [MemoryStatus.in_progress], limit: 1);
    _inProgressMemory = memories.isNotEmpty ? memories.first : null;
    if (_inProgressMemory != null) {
      segments = _inProgressMemory!.transcriptSegments;
      setHasTranscripts(segments.isNotEmpty);
    }
    notifyListeners();
  }

  @override
  void onMessageEventReceived(ServerMessageEvent event) {
    if (event.type == MessageEventType.memoryProcessingStarted) {
      if (event.memory == null) {
        debugPrint("Memory data not received in event. Content is: $event");
        return;
      }
      memoryProvider!.addProcessingMemory(event.memory!);
      _resetStateVariables();
      return;
    }

    if (event.type == MessageEventType.memoryCreated) {
      if (event.memory == null) {
        debugPrint("Memory data not received in event. Content is: $event");
        return;
      }
      event.memory!.isNew = true;
      memoryProvider!.removeProcessingMemory(event.memory!.id);
      _processMemoryCreated(event.memory, event.messages ?? []);
      return;
    }
  }

  Future<void> forceProcessingCurrentMemory() async {
    _resetStateVariables();
    memoryProvider!.addProcessingMemory(
      ServerMemory(id: '0', createdAt: DateTime.now(), structured: Structured('', ''), status: MemoryStatus.processing),
    );
    processInProgressMemory().then((result) {
      if (result == null || result.memory == null) {
        _initiateWebsocket();
        memoryProvider!.removeProcessingMemory('0');
        return;
      }
      memoryProvider!.removeProcessingMemory('0');
      result.memory!.isNew = true;
      _processMemoryCreated(result.memory, result.messages);
      _initiateWebsocket();
    });

    return;
  }

  Future<void> _processMemoryCreated(ServerMemory? memory, List<ServerMessage> messages) async {
    if (memory == null) return;
    memoryProvider?.upsertMemory(memory);
    MixpanelManager().memoryCreated(memory);
  }

  @override
  void onSegmentReceived(List<TranscriptSegment> newSegments) {
    if (newSegments.isEmpty) return;

    if (segments.isEmpty) {
      debugPrint('newSegments: ${newSegments.last}');
      FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
      _loadInProgressMemory();
    }
    TranscriptSegment.combineSegments(segments, newSegments);
    hasTranscripts = true;
    notifyListeners();
  }

  void onInternetSatusChanged(InternetStatus status) {
    debugPrint("[SocketService] Internet connection changed $status");
    _internetStatus = status;
    notifyListeners();
  }

  void setIsWalSupported(bool value) {
    _isWalSupported = value;
    notifyListeners();
  }

  /*
  *
  *
  *
  *
  *
  * */

  List<int> currentStorageFiles = <int>[];
  int sdCardFileNum = 1;

// To show the progress of the download in the UI
  int currentTotalBytesReceived = 0;
  double currentSdCardSecondsReceived = 0.0;
//--------------------------------------------

  int totalStorageFileBytes = 0; // how much in storage
  int totalBytesReceived = 0; // how much already received
  double sdCardSecondsTotal = 0.0; // time to send the next chunk
  double sdCardSecondsReceived = 0.0;
  bool sdCardDownloadDone = false;
  bool sdCardReady = false;
  bool sdCardIsDownloading = false;
  String btConnectedTime = "";
  Timer? sdCardReconnectionTimer;

  void setSdCardIsDownloading(bool value) {
    sdCardIsDownloading = value;
    notifyListeners();
  }

  Future<void> updateStorageList() async {
    currentStorageFiles = await _getStorageList(_recordingDevice!.id);
    if (currentStorageFiles.isEmpty) {
      debugPrint('No storage files found');
      SharedPreferencesUtil().deviceIsV2 = false;
      debugPrint('Device is not V2');
      return;
    }
    totalStorageFileBytes = currentStorageFiles[0];
    var storageOffset = currentStorageFiles.length < 2 ? 0 : currentStorageFiles[1];
    totalBytesReceived = storageOffset;
    notifyListeners();
  }

  Future<void> initiateStorageBytesStreaming() async {
    debugPrint('initiateStorageBytesStreaming');
    if (_recordingDevice == null) return;
    var storageFiles = await _getStorageList(_recordingDevice!.id);
    if (storageFiles.isEmpty) {
      return;
    }
    var totalBytes = storageFiles[0];
    if (totalBytes <= 0) {
      return;
    }
    var storageOffset = storageFiles.length < 2 ? 0 : storageFiles[1];
    if (storageOffset > totalBytes) {
      // bad state?
      debugPrint("SDCard bad state, offset > total");
      storageOffset = 0;
    }

    // 80: frame length, 100: frame per seconds
    sdCardSecondsTotal = totalBytes / 80 / 100;
    sdCardSecondsReceived = storageOffset / 80 / 100;

    // > 10s
    if (totalBytes - storageOffset > 10 * 80 * 100) {
      sdCardReady = true;
    }

    notifyListeners();

    /* TODO: Remove
    if (_recordingDevice == null) return;
    currentStorageFiles = await _getStorageList(_recordingDevice!.id);
    if (currentStorageFiles.isEmpty) {
      debugPrint('No storage files found');
      SharedPreferencesUtil().deviceIsV2 = false;
      debugPrint('Device is not V2');
      return;
    }
    SharedPreferencesUtil().deviceIsV2 = true;
    debugPrint('Device is V2');
    debugPrint('Device model name: ${_recordingDevice!.name}');
    debugPrint('Storage files: $currentStorageFiles');
    totalStorageFileBytes = currentStorageFiles[0];
    var storageOffset = currentStorageFiles.length < 2 ? 0 : currentStorageFiles[1];
    debugPrint('storageOffset: $storageOffset');
    // SharedPreferencesUtil().previousStorageBytes = totalStorageFileBytes;
    //check if new or old file
    if (totalStorageFileBytes < SharedPreferencesUtil().previousStorageBytes) {
      totalBytesReceived = 0;
      currentTotalBytesReceived = 0;
      SharedPreferencesUtil().currentStorageBytes = 0;
    } else {
      totalBytesReceived = SharedPreferencesUtil().currentStorageBytes;
    }
    if (totalBytesReceived > totalStorageFileBytes) {
      totalBytesReceived = 0;
      currentTotalBytesReceived = 0;
    }
    totalBytesReceived = storageOffset;
    SharedPreferencesUtil().previousStorageBytes = totalStorageFileBytes;
    sdCardSecondsTotal =
        ((totalStorageFileBytes.toDouble() / 80.0) / 100.0) * 2.2; // change 2.2 depending on empirical dl speed
    sdCardSecondsReceived = ((storageOffset.toDouble() / 80.0) / 100.0) * 2.2;
    currentSdCardSecondsReceived = 0.0;
    debugPrint('totalBytesReceived in initiateStorageBytesStreaming: $totalBytesReceived');
    debugPrint(
        'previousStorageBytes in initiateStorageBytesStreaming: ${SharedPreferencesUtil().previousStorageBytes}');
    btConnectedTime = DateTime.now().toUtc().toString();

    if (totalStorageFileBytes > 100) {
      sdCardReady = true;
    }
    notifyListeners();
		*/
  }

  @Deprecated("Unsued")
  Future sendStorage(String id) async {
    if (_storageStream != null) {
      _storageStream?.cancel();
    }
    if (totalStorageFileBytes == 0) {
      return;
    }
    await sdCardSocket.setupSdCardWebSocket(
      //replace
      onMessageReceived: () {
        debugPrint('onMessageReceived');
        memoryProvider?.getMemoriesFromServer();
        notifyListeners();
        _notifySdCardComplete();
        return;
      },
      btConnectedTime: btConnectedTime,
    );
    if (sdCardSocket.sdCardConnectionState != WebsocketConnectionStatus.connected) {
      sdCardSocket.sdCardChannel?.sink.close();
      await sdCardSocket.setupSdCardWebSocket(
        onMessageReceived: () {
          debugPrint('onMessageReceived');
          memoryProvider?.getMoreMemoriesFromServer();
          _notifySdCardComplete();

          return;
        },
        btConnectedTime: btConnectedTime,
      );
    }
    // debugPrint('sd card connection state: ${sdCardSocketService?.sdCardConnectionState}');
    _storageStream = await _getBleStorageBytesListener(id, onStorageBytesReceived: (List<int> value) async {
      if (value.isEmpty) return;

      if (value.length == 1) {
        //result codes i guess
        debugPrint('returned $value');
        if (value[0] == 0) {
          //valid command
          DateTime storageStartTime = DateTime.now();
          debugPrint('good to go');
        } else if (value[0] == 3) {
          debugPrint('bad file size. finishing...');
        } else if (value[0] == 4) {
          //file size is zero.
          debugPrint('file size is zero. going to next one....');
          // getFileFromDevice(sdCardFileNum + 1);
        } else if (value[0] == 100) {
          //valid end command

          sdCardDownloadDone = true;
          sdCardIsDownloading = false;
          debugPrint('done. sending to backend....trying to dl more');

          sdCardSocket.sdCardChannel?.sink.add(value); //replace
          SharedPreferencesUtil().currentStorageBytes = 0;
          SharedPreferencesUtil().previousStorageBytes = 0;
          _clearFileFromDevice(sdCardFileNum);
        } else {
          //bad bit
          debugPrint('Error bit returned');
        }
      } else if (value.length >= 80) {
        //enforce a min packet size, large
        if (value.length == 83) {
          totalBytesReceived += 80;
          currentTotalBytesReceived += 80;
        } else {
          totalBytesReceived += value.length;
          currentTotalBytesReceived += value.length;
        }
        if (sdCardSocket.sdCardConnectionState != WebsocketConnectionStatus.connected) {
          debugPrint('websocket provider state: ${sdCardSocket.sdCardConnectionState}');
          //means we are disconnected, stop all transmission. attempt reconnection
          if (!sdCardIsDownloading) {
            debugPrint('sdCardIsDownloading: $sdCardIsDownloading');
            return;
          }
          sdCardIsDownloading = false;
          _pauseFileFromDevice(sdCardFileNum);
          debugPrint('paused file from device');
          //attempt reconnection
          sdCardSocket.sdCardChannel?.sink.close();
          sdCardSocket.attemptReconnection(
            onMessageReceived: () {
              debugPrint('onMessageReceived');
              memoryProvider?.getMoreMemoriesFromServer();
              _notifySdCardComplete();
              return;
            },
            btConnectedTime: btConnectedTime,
          );
          sdCardReconnectionTimer?.cancel();
          sdCardReconnectionTimer = Timer(const Duration(seconds: 10), () {
            debugPrint('sdCardReconnectionTimer');
            if (sdCardSocket.sdCardConnectionState == WebsocketConnectionStatus.connected) {
              sdCardIsDownloading = true;
              _getFileFromDevice(sdCardFileNum, totalBytesReceived);
            }
          });

          //call attempt reconnection
          return;
        }

        sdCardSocket.sdCardChannel?.sink.add(value);
        sdCardSecondsReceived = ((totalBytesReceived.toDouble() / 80.0) / 100.0) * 2.2;
        currentSdCardSecondsReceived = ((currentTotalBytesReceived.toDouble() / 80.0) / 100.0) * 2.2;
        SharedPreferencesUtil().currentStorageBytes = totalBytesReceived;
      }
      notifyListeners();
    });

    _getFileFromDevice(sdCardFileNum, totalBytesReceived);
    //  notifyListeners();
  }

  Future _getFileFromDevice(int fileNum, int offset) async {
    sdCardFileNum = fileNum;
    int command = 0;
    _writeToStorage(_recordingDevice!.id, sdCardFileNum, command, offset);
  }

  Future _clearFileFromDevice(int fileNum) async {
    sdCardFileNum = fileNum;
    int command = 1;
    _writeToStorage(_recordingDevice!.id, sdCardFileNum, command, 0);
  }

  Future _pauseFileFromDevice(int fileNum) async {
    sdCardFileNum = fileNum;
    int command = 3;
    _writeToStorage(_recordingDevice!.id, sdCardFileNum, command, 0);
  }

  void _notifySdCardComplete() {
    NotificationService.instance.clearNotification(8);
    NotificationService.instance.createNotification(
      notificationId: 8,
      title: 'Sd Card Processing Complete',
      body: 'Your Sd Card data is now processed! Enter the app to see.',
    );
  }

  Future<bool> _writeToStorage(String deviceId, int numFile, int command, int offset) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(false);
    }
    return connection.writeToStorage(numFile, command, offset);
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  void _setsdCardReady(bool value) {
    sdCardReady = value;
    notifyListeners();
  }
}
