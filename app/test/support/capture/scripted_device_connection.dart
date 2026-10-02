import 'dart:async';

import 'package:omi/services/devices/connectors/device_connection.dart';

/// A pendant BLE link for capture scenarios: the controller subscribes to its audio exactly as it
/// subscribes to a real connection, and the test pushes frames with [emitAudio]. It records how many
/// audio subscriptions are open, so a scenario can tell whether the pendant is streaming.
class ScriptedDeviceConnection implements DeviceConnection {
  final _audio = StreamController<List<int>>.broadcast(sync: true);
  int audioSubscriptionsOpened = 0;
  int _open = 0;

  /// Audio subscriptions the controller currently holds.
  int get openAudioSubscriptions => _open;

  /// A BLE audio packet: a 3-byte header then [payloadLength] bytes of [value].
  void emitAudio({int value = 7, int payloadLength = 80}) {
    _audio.add([0, 0, 0, ...List<int>.filled(payloadLength, value)]);
  }

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
