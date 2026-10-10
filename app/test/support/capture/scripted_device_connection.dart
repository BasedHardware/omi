import 'dart:async';

import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// A pendant BLE link for capture scenarios: the controller subscribes to its audio exactly as it
/// subscribes to a real connection, and the test pushes frames with [emitAudio]. It records how many
/// audio subscriptions are open, so a scenario can tell whether the pendant is streaming.
class ScriptedDeviceConnection implements DeviceConnection {
  @override
  final _ScriptedTransport transport = _ScriptedTransport();

  void emitSubscriptionFailure() => transport.errors.add(StateError('CCCD failed'));
  final _audio = StreamController<List<int>>.broadcast(sync: true);
  final _taps = StreamController<List<int>>.broadcast(sync: true);

  /// Feature bits the pendant reports. 0 is firmware that does not report tap counts.
  int features = 0;
  int audioSubscriptionsOpened = 0;
  int _open = 0;

  /// Audio subscriptions the controller currently holds.
  int get openAudioSubscriptions => _open;

  /// A BLE audio packet: a 3-byte header then [payloadLength] bytes of [value].
  void emitAudio({int value = 7, int payloadLength = 80}) {
    emitRawAudio([0, 0, 0, ...List<int>.filled(payloadLength, value)]);
  }

  /// Emit a caller-owned packet so capture tests can exercise buffer reuse.
  void emitRawAudio(List<int> packet) => _audio.add(packet);

  /// A tap-count notification: `[1, n]` when tap n is released, `[2, n]` when the sequence ends.
  void emitTaps(List<int> packet) => _taps.add(packet);

  @override
  Future<StreamSubscription?> getBleAudioBytesListener({required void Function(List<int>) onAudioBytesReceived}) async {
    audioSubscriptionsOpened++;
    _open++;
    var cancelled = false;
    final subscription = _audio.stream.listen(onAudioBytesReceived);
    return _CountingSubscription(subscription, () {
      if (cancelled) return;
      cancelled = true;
      _open--;
    });
  }

  @override
  Future<StreamSubscription?> getBleButtonListener({required void Function(List<int>) onButtonReceived}) async => null;

  @override
  Future<StreamSubscription?> getBleButtonTapsListener({required void Function(List<int>) onTapsReceived}) async =>
      _taps.stream.listen(onTapsReceived);

  @override
  Future<int> getFeatures() async => features;

  @override
  Future<bool> hasPhotoStreamingCharacteristic() async => false;

  @override
  Future<void> onNetworkSocketReconnected() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _CountingSubscription<T> implements StreamSubscription<T> {
  _CountingSubscription(this._inner, this._onCancel);
  final StreamSubscription<T> _inner;
  final void Function() _onCancel;

  @override
  Future<void> cancel() {
    _onCancel();
    return _inner.cancel();
  }

  @override
  void onData(void Function(T data)? handleData) => _inner.onData(handleData);
  @override
  void onError(Function? handleError) => _inner.onError(handleError);
  @override
  void onDone(void Function()? handleDone) => _inner.onDone(handleDone);
  @override
  void pause([Future<void>? resumeSignal]) => _inner.pause(resumeSignal);
  @override
  void resume() => _inner.resume();
  @override
  bool get isPaused => _inner.isPaused;
  @override
  Future<E> asFuture<E>([E? futureValue]) => _inner.asFuture<E>(futureValue);
}

class _ScriptedTransport implements DeviceTransport, CaptureSubscriptionErrors {
  final errors = StreamController<Object>.broadcast(sync: true);
  @override
  Stream<Object> get audioSubscriptionErrors => errors.stream;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
