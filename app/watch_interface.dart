import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(
  dartOut: 'lib/src/flutter_communicator.g.dart',
  dartOptions: DartOptions(),
  swiftOut: 'ios/Runner/FlutterCommunicator.g.swift',
  swiftOptions: SwiftOptions(),
  dartPackageName: 'watch',
))
@HostApi()
abstract class WatchCounterHostAPI {
  @SwiftFunction('increment()')
  void increment();
  @SwiftFunction('decrement()')
  void decrement();
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
}

@FlutterApi()
abstract class WatchCounterFlutterAPI {
  void increment();
  void decrement();
  void onRecordingStarted();
  void onRecordingStopped();
  void onAudioData(Uint8List audioData);
  void onAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate);
}
