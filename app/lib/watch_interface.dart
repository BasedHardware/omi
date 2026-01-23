import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(
  dartOut: 'lib/gen/flutter_communicator.g.dart',
  dartOptions: DartOptions(),
  swiftOut: 'ios/Runner/FlutterCommunicator.g.swift',
  swiftOptions: SwiftOptions(),
  dartPackageName: 'watch',
))
@HostApi()
abstract class WatchRecorderHostAPI {
  @SwiftFunction('startRecording()')
  void startRecording();
  @SwiftFunction('stopRecording()')
  void stopRecording();
  @SwiftFunction('sendAudioData(audioData:)')
  void sendAudioData(Uint8List audioData);
  @SwiftFunction('sendAudioChunk(audioChunk:chunkIndex:isLast:sampleRate:)')
  void sendAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate);
  @SwiftFunction('isWatchPaired()')
  bool isWatchPaired();
  @SwiftFunction('isWatchReachable()')
  bool isWatchReachable();
  @SwiftFunction('isWatchSessionSupported()')
  bool isWatchSessionSupported();
  @SwiftFunction('isWatchAppInstalled()')
  bool isWatchAppInstalled();
  @SwiftFunction('requestWatchMicrophonePermission()')
  void requestWatchMicrophonePermission();
  @SwiftFunction('requestMainAppMicrophonePermission()')
  void requestMainAppMicrophonePermission();
  @SwiftFunction('checkMainAppMicrophonePermission()')
  bool checkMainAppMicrophonePermission();
  @SwiftFunction('getWatchBatteryLevel()')
  double getWatchBatteryLevel();
  @SwiftFunction('getWatchBatteryState()')
  int getWatchBatteryState();
  @SwiftFunction('requestWatchBatteryUpdate()')
  void requestWatchBatteryUpdate();
  @SwiftFunction('getWatchInfo()')
  Map<String, String> getWatchInfo();
}

@FlutterApi()
abstract class WatchRecorderFlutterAPI {
  void onRecordingStarted();
  void onRecordingStopped();
  void onAudioData(Uint8List audioData);
  void onAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate);
  void onRecordingError(String error);
  void onMicrophonePermissionResult(bool granted);
  void onMainAppMicrophonePermissionResult(bool granted);
  void onWatchBatteryUpdate(double batteryLevel, int batteryState);
}
