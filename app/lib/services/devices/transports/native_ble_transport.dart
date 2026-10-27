import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'device_transport.dart';

/// After subscribing, one CCCD re-subscribe is allowed if no audio bytes arrive.
const _captureAudioLivenessWindow = Duration(seconds: 4);
const _captureAudioSilenceResubscribeLimit = 1;

/// BLE transport backed by native platform APIs via Pigeon.
/// Uses the intent-based manageDevice/unmanageDevice API.
/// Native owns the connection lifecycle (retry, reconnect, bonding).
/// This transport is long-lived
class NativeBleTransport extends DeviceTransport implements CaptureSubscriptionErrors {
  /// Installed by capture. Counts audio notifications as they arrive so a
  /// silent GATT link is distinct from a socket that sent nothing.
  static void Function(String deviceId, int byteCount)? ingressByteObserver;

  bool savedReconnectEnabled = false;
  bool hasRetryableConnectFailure = false;
  Future<void>? _connectInFlight;

  final String _peripheralUuid;
  final bool requiresBond;
  final BleHostApi _hostApi;
  final StreamController<DeviceTransportState> _connectionStateController =
      StreamController<DeviceTransportState>.broadcast();

  /// Characteristic notification streams, keyed by "serviceUuid:charUuid" (lowercased).
  final Map<String, StreamController<List<int>>> _streamControllers = {};

  /// Discovered services from native.
  List<BleService> _services = [];

  Completer<List<BleService>>? _deviceReadyCompleter;

  DeviceTransportState _state = DeviceTransportState.disconnected;
  late final VoidCallback _releaseBridge;

  /// Set when [disconnect] hands the peripheral back to native, cleared by
  /// [connect]. Native keeps connecting and reconnecting after a Dart-side
  /// timeout or drop, so release cannot be inferred from the mirrored [_state].
  bool _nativeReleased = false;
  // True only while disconnect() awaits unmanageDevice: a ready arriving in
  // this window is buffered in [_readyWhileReleasing] because a failed release
  // must replay it (native kept the link), while a successful one discards it.
  bool _releasePending = false;
  List<BleService>? _readyWhileReleasing;
  Timer? _audioLivenessTimer;
  int _audioSilenceResubscribes = 0;
  int _subscriptionGeneration = 0;
  bool _nativeIngressOwned = false;
  final Map<String, Object> subscriptionFailures = {};
  final _audioSubscriptionErrors = StreamController<Object>.broadcast();
  @override
  Stream<Object> get audioSubscriptionErrors => Stream.multi((consumer) {
        final subscription = _audioSubscriptionErrors.stream.listen(consumer.add, onDone: consumer.close);
        // Some adapters subscribe during connection setup, before capture binds.
        // Replay only failures belonging to the current connection generation.
        for (final entry in subscriptionFailures.entries) {
          if (isBleAudioCharacteristicUuid(entry.key.split(':').last)) consumer.add(entry.value);
        }
        consumer.onCancel = subscription.cancel;
      }, isBroadcast: true);
  final Map<String, int> _pendingSubscriptions = {};

  bool _nativeOwnsAudioHealth(String characteristicUuid) =>
      defaultTargetPlatform == TargetPlatform.iOS &&
      BleBridge.instance.nativeOwnsIngress(_peripheralUuid) &&
      characteristicUuid.toLowerCase() == '19b10001-e8f2-537e-4f6c-d104768a1214';

  NativeBleTransport(this._peripheralUuid, {this.requiresBond = false, BleHostApi? hostApi})
      : _hostApi = hostApi ?? BleHostApi() {
    BleBridge.instance.addIngressListener(_ingressOwnershipChanged);
    _releaseBridge = BleBridge.instance.registerPeripheral(
      peripheralUuid: _peripheralUuid,
      onConnectionState: _handleConnectionState,
      onDeviceReady: _handleDeviceReady,
      onCharacteristicValue: _handleCharacteristicValue,
    );
  }

  @override
  String get deviceId => _peripheralUuid;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _connectionStateController.stream;

  // MARK: - Connection

  @override
  Future<void> connect() => _connectInFlight ??= _connect().whenComplete(() => _connectInFlight = null);

  Future<void> _connect() async {
    hasRetryableConnectFailure = true;
    if (_state == DeviceTransportState.connected && await isConnected()) return;

    if (!await BluetoothReadiness.instance.ensureReady(BluetoothUse.connection)) {
      throw BluetoothAdapterUnavailableException(BluetoothReadiness.instance.state);
    }

    _updateState(DeviceTransportState.connecting);

    _deviceReadyCompleter = Completer<List<BleService>>();
    final deviceReady = _deviceReadyCompleter!.future;
    // A disconnect can arrive while the platform's manageDevice reply is pending.
    // Observe that error immediately; the await below still delivers it to connect's caller.
    deviceReady.ignore();

    try {
      _nativeReleased = false;
      await _hostApi.manageDevice(_peripheralUuid, requiresBond);
    } catch (e) {
      Logger.debug('[NativeBleTransport] manageDevice failed: $e');
      _deviceReadyCompleter = null;
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }

    try {
      _services = await deviceReady.timeout(
        const Duration(seconds: 60),
        onTimeout: () => throw TimeoutException('Device ready timeout after 60s'),
      );
      _deviceReadyCompleter = null;
      _updateState(DeviceTransportState.connected);
    } catch (e) {
      Logger.debug('[NativeBleTransport] connect failed: $e');
      _deviceReadyCompleter = null;
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<void> disconnect() async {
    if (_deviceReadyCompleter case final completer? when !completer.isCompleted) {
      completer.completeError('unmanaged');
    }
    _subscriptionGeneration++;
    if (_nativeReleased && _state == DeviceTransportState.disconnected && _streamControllers.isEmpty) return;

    // A liveness watch pending from a prior connection must not fire into a
    // subsequent one and force a spurious CCCD re-subscribe.
    _audioLivenessTimer?.cancel();
    _audioSilenceResubscribes = 0;

    _updateState(DeviceTransportState.disconnecting);

    // Unsubscribe all active streams
    for (final key in _activeSubscriptionKeys.toList()) {
      final parts = key.split(':');
      if (parts.length == 2) {
        try {
          _hostApi.unsubscribeCharacteristic(_peripheralUuid, parts[0], parts[1]);
        } catch (_) {}
      }
    }

    _activeSubscriptionKeys.clear();
    _subscribedSubscriptionKeys.clear();
    _closeAllStreams();
    _services = [];

    List<BleService>? replayReady;
    try {
      _nativeReleased = true;
      _releasePending = true;
      await _hostApi.unmanageDevice(_peripheralUuid);
      _releasePending = false;
      _readyWhileReleasing = null;
    } catch (e) {
      // Native may still own the link; keep release retryable and its readies
      // adoptable rather than mirroring "released" over a live link. A ready
      // that arrived while the release was pending is still native's word that
      // the link is live, so replay it below — after disconnect's final state,
      // exactly like a ready arriving after a failed release.
      _releasePending = false;
      _nativeReleased = false;
      replayReady = _readyWhileReleasing;
      _readyWhileReleasing = null;
      Logger.debug('[NativeBleTransport] unmanageDevice failed: $e');
    }

    _updateState(DeviceTransportState.disconnected);
    if (replayReady != null) _handleDeviceReady(replayReady);
  }

  @override
  Future<bool> isConnected() async {
    try {
      return await _hostApi.isPeripheralConnected(_peripheralUuid);
    } catch (e) {
      return false;
    }
  }

  @override
  Future<bool> ping() async {
    try {
      return await _hostApi.isPeripheralConnected(_peripheralUuid);
    } catch (e) {
      return false;
    }
  }

  @override
  Future<bool> requestBond() async {
    try {
      return await _hostApi.requestBond(_peripheralUuid);
    } catch (e) {
      Logger.debug('[NativeBleTransport] requestBond failed: $e');
      return false;
    }
  }

  // MARK: - Characteristic Streams

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    final key = '${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _activeSubscriptionKeys.add(key);
      if (_state == DeviceTransportState.connected) {
        unawaited(_subscribeCharacteristic(serviceUuid, characteristicUuid));
      }
    }

    return _streamControllers[key]!.stream;
  }

  // Bound missing native callbacks without changing the platform's GATT lifetime.
  static const subscriptionTimeout = Duration(seconds: 20);

  Future<void> _subscribeCharacteristic(String serviceUuid, String characteristicUuid, {bool force = false}) async {
    final key = '${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}';
    if (!force && _subscribedSubscriptionKeys.contains(key)) return;
    final generation = _subscriptionGeneration;
    if (_pendingSubscriptions[key] == generation) return;
    _pendingSubscriptions[key] = generation;
    Object? failure;
    try {
      if (isBleAudioCharacteristicUuid(characteristicUuid)) {
        final gate = beforeAudioResubscribe;
        if (gate != null) await gate(characteristicUuid);
        if (generation != _subscriptionGeneration) return;
      }
      await _hostApi.subscribeCharacteristic(_peripheralUuid, serviceUuid, characteristicUuid).then((_) {
        if (generation == _subscriptionGeneration &&
            failure is TimeoutException &&
            identical(subscriptionFailures[key], failure)) {
          subscriptionFailures.remove(key);
        }
      }).timeout(subscriptionTimeout);
      if (generation != _subscriptionGeneration) return;
      _subscribedSubscriptionKeys.add(key);
      subscriptionFailures.remove(key);
      if (isBleAudioCharacteristicUuid(characteristicUuid) && !_nativeOwnsAudioHealth(characteristicUuid)) {
        _armAudioLivenessWatch();
      }
    } catch (e) {
      if (generation != _subscriptionGeneration) return;
      _subscribedSubscriptionKeys.remove(key);
      failure = e;
      subscriptionFailures[key] = e;
      if (isBleAudioCharacteristicUuid(characteristicUuid)) {
        _audioSubscriptionErrors.add(e);
        if (!_nativeOwnsAudioHealth(characteristicUuid)) _armAudioLivenessWatch();
      }
      Logger.debug('[NativeBleTransport] Failed to subscribe $serviceUuid:$characteristicUuid: $e');
    } finally {
      if (_pendingSubscriptions[key] == generation) _pendingSubscriptions.remove(key);
    }
  }

  bool _hasCharacteristic(String serviceUuid, String characteristicUuid) {
    final sUuid = serviceUuid.toLowerCase();
    final cUuid = characteristicUuid.toLowerCase();
    for (final service in _services) {
      if (service.uuid.toLowerCase() == sUuid) {
        return service.characteristicUuids.any((c) => c.toLowerCase() == cUuid);
      }
    }
    return false;
  }

  /// Returns whether the currently discovered GATT table exposes a characteristic.
  ///
  /// This is intentionally read-only so higher-level commands can fail closed
  /// instead of treating NativeBleTransport's compatibility no-op writes as success.
  bool hasCharacteristic(String serviceUuid, String characteristicUuid) =>
      _hasCharacteristic(serviceUuid, characteristicUuid);

  /// A connected pendant can leave a GATT read or write unanswered (and older
  /// native code orphaned a second same-characteristic read). Every awaited
  /// operation is bounded so a capture or sync pass can never wait forever.
  @visibleForTesting
  static Duration operationTimeout = const Duration(seconds: 10);

  void _logOperationTimeout(String op, String characteristicUuid) {
    Logger.debug('[NativeBleTransport] $op $characteristicUuid timed out after ${operationTimeout.inSeconds}s');
    unawaited(DebugLogManager.logWarning('ble_op_timeout', {'op': op, 'characteristic': characteristicUuid}));
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (!_hasCharacteristic(serviceUuid, characteristicUuid)) return [];
    try {
      final data = await _hostApi.readCharacteristic(_peripheralUuid, serviceUuid, characteristicUuid).timeout(
            operationTimeout,
          );
      return data.toList();
    } on TimeoutException {
      _logOperationTimeout('read', characteristicUuid);
      return [];
    } catch (e) {
      Logger.debug('[NativeBleTransport] Failed to read $serviceUuid:$characteristicUuid: $e');
      return [];
    }
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    if (!_hasCharacteristic(serviceUuid, characteristicUuid)) {
      Logger.debug('[NativeBleTransport] writeCharacteristic skipped: $characteristicUuid not available');
      return;
    }
    try {
      await _hostApi
          .writeCharacteristic(_peripheralUuid, serviceUuid, characteristicUuid, Uint8List.fromList(data))
          .timeout(operationTimeout);
    } on TimeoutException {
      _logOperationTimeout('write', characteristicUuid);
      rethrow;
    } catch (e) {
      Logger.debug('[NativeBleTransport] Failed to write characteristic: $e');
      rethrow;
    }
  }

  // MARK: - Dispose

  @override
  Future<void> dispose() async {
    _subscriptionGeneration++;
    _audioLivenessTimer?.cancel();
    BleBridge.instance.removeIngressListener(_ingressOwnershipChanged);
    _releaseBridge();
    await _audioSubscriptionErrors.close();
    _activeSubscriptionKeys.clear();
    _subscribedSubscriptionKeys.clear();
    _closeAllStreams();
    await _connectionStateController.close();
  }

  // MARK: - Private Helpers

  void _updateState(DeviceTransportState newState) {
    if (_state != newState && !_connectionStateController.isClosed) {
      _state = newState;
      _connectionStateController.add(_state);
    }
  }

  void _closeAllStreams() {
    for (final controller in _streamControllers.values) {
      controller.close();
    }
    _streamControllers.clear();
  }

  void _addToStream(String serviceUuid, String characteristicUuid, List<int> data) {
    final key = '${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}';
    final controller = _streamControllers[key];
    if (controller != null && !controller.isClosed && controller.hasListener) {
      controller.add(data);
    } else if (characteristicUuid.toLowerCase() == audioDataStreamCharacteristicUuid) {
      // Native stays subscribed after capture cancels its listener, and the
      // pendant then streams instead of storing. Never drop those packets.
      OrphanAudioRoute.deliver(deviceId, data);
    }
  }

  // MARK: - Native Callbacks

  /// Track which characteristics were subscribed so we can re-subscribe on reconnect.
  final Set<String> _activeSubscriptionKeys = {};
  final Set<String> _subscribedSubscriptionKeys = {};

  void _handleConnectionState(bool connected, String? error) {
    if (!connected) {
      hasRetryableConnectFailure = error != 'pairing_lost' && error != 'unmanaged';
      _subscriptionGeneration++;
      // Guard against double-fire (didDisconnect + didFailToConnect both invoke this).
      // On the 2nd call _streamControllers is already empty; overwriting _activeSubscriptionKeys
      // with {} would prevent re-subscription on the next reconnect.
      if (_streamControllers.isNotEmpty) {
        _activeSubscriptionKeys.addAll(_streamControllers.keys);
      } else {
        _activeSubscriptionKeys.clear();
      }

      _subscribedSubscriptionKeys.clear();
      subscriptionFailures.clear();
      _audioLivenessTimer?.cancel();
      _audioSilenceResubscribes = 0;
      _services = [];
      _updateState(DeviceTransportState.disconnected);

      // Fail pending completer
      if (_deviceReadyCompleter != null && !_deviceReadyCompleter!.isCompleted) {
        _deviceReadyCompleter!.completeError(error ?? 'Disconnected before ready');
      }
    }
  }

  void _handleDeviceReady(List<BleService> services) {
    // A ready already in flight when this transport released native must not
    // re-adopt the link behind the explicit disconnect. If a release is still
    // pending, buffer the ready: a failed release replays it (native kept the
    // link), a successful one discards it.
    if (_nativeReleased) {
      if (_readyWhileReleasing == null && _releasePending) _readyWhileReleasing = services;
      return;
    }
    hasRetryableConnectFailure = false;
    _subscriptionGeneration++;
    _subscribedSubscriptionKeys.clear();
    subscriptionFailures.clear();
    if (_deviceReadyCompleter != null && !_deviceReadyCompleter!.isCompleted) {
      // Initial connection
      _services = services;
      _deviceReadyCompleter!.complete(services);
      _subscribeActiveCharacteristics();
    } else {
      // Auto-reconnect from native — re-subscribe to characteristics
      _resubscribeAfterReconnect(services);
    }
  }

  bool _isResubscribing = false;

  void _subscribeActiveCharacteristics() {
    for (final key in _activeSubscriptionKeys) {
      final parts = key.split(':');
      if (parts.length == 2) {
        unawaited(_subscribeCharacteristic(parts[0], parts[1]));
      }
    }
  }

  Future<void> Function(String characteristicUuid)? beforeAudioResubscribe;

  void _resubscribeAfterReconnect(List<BleService> services) {
    if (_isResubscribing) return;
    _isResubscribing = true;

    try {
      _services = services;

      // Native re-emits ready for a link that is already up, so keep live controllers.
      final controlSubscriptions = <Future<void>>[];
      for (final key in _activeSubscriptionKeys) {
        final parts = key.split(':');
        if (parts.length == 2) {
          final controller = _streamControllers[key];
          if (controller == null || controller.isClosed) {
            _streamControllers[key] = StreamController<List<int>>.broadcast();
          }
          if (!isBleAudioCharacteristicUuid(parts[1])) {
            controlSubscriptions.add(_subscribeCharacteristic(parts[0], parts[1]));
          }
        }
      }
      unawaited(
        Future.wait(controlSubscriptions).then((_) {
          for (final key in _activeSubscriptionKeys) {
            final parts = key.split(':');
            if (parts.length != 2 || !isBleAudioCharacteristicUuid(parts[1])) continue;
            unawaited(_subscribeCharacteristic(parts[0], parts[1]));
          }
        }),
      );

      _updateState(DeviceTransportState.connected);
      _audioSilenceResubscribes = 0;
      _armAudioLivenessWatch();
    } catch (e) {
      Logger.debug('[NativeBleTransport] Failed to re-subscribe after reconnect: $e');
      _updateState(DeviceTransportState.disconnected);
    } finally {
      _isResubscribing = false;
    }
  }

  void _handleCharacteristicValue(String serviceUuid, String characteristicUuid, Uint8List value) {
    if (isBleAudioCharacteristicUuid(characteristicUuid) && value.isNotEmpty) {
      _audioSilenceResubscribes = 0;
      _audioLivenessTimer?.cancel();
      ingressByteObserver?.call(deviceId, value.length);
    }
    _addToStream(serviceUuid, characteristicUuid, value);
  }

  bool get _hasAudioSubscription {
    return _activeSubscriptionKeys.any((key) {
      final parts = key.split(':');
      return parts.length == 2 &&
          _streamControllers[key]?.hasListener == true &&
          isBleAudioCharacteristicUuid(parts[1]) &&
          !_nativeOwnsAudioHealth(parts[1]);
    });
  }

  void _ingressOwnershipChanged() {
    final owned = _nativeOwnsAudioHealth(audioDataStreamCharacteristicUuid);
    if (owned == _nativeIngressOwned) return;
    _nativeIngressOwned = owned;
    if (!_hasAudioSubscription) {
      _audioLivenessTimer?.cancel();
    } else if (_audioLivenessTimer?.isActive != true) {
      _armAudioLivenessWatch();
    }
  }

  void _armAudioLivenessWatch() {
    _audioLivenessTimer?.cancel();
    if (_state != DeviceTransportState.connected || !_hasAudioSubscription) {
      return;
    }
    _audioLivenessTimer = Timer(_captureAudioLivenessWindow, _onAudioLivenessTimeout);
  }

  void _onAudioLivenessTimeout() {
    if (_state != DeviceTransportState.connected || !_hasAudioSubscription) return;
    // Waiting for the native confirmation is not a retry. In particular its
    // confirmation wait must not consume the one retry at the 4-second watch.
    if (_pendingSubscriptions.entries.any(
      (entry) => entry.value == _subscriptionGeneration && isBleAudioCharacteristicUuid(entry.key.split(':').last),
    )) {
      _armAudioLivenessWatch();
      return;
    }
    if (_audioSilenceResubscribes < _captureAudioSilenceResubscribeLimit) {
      _audioSilenceResubscribes++;
      Logger.debug('[NativeBleTransport] no audio after reconnect, retrying CCCD subscribe once');
      for (final key in _activeSubscriptionKeys) {
        final parts = key.split(':');
        if (parts.length == 2 && isBleAudioCharacteristicUuid(parts[1]) && !_nativeOwnsAudioHealth(parts[1])) {
          unawaited(_subscribeCharacteristic(parts[0], parts[1], force: true));
        }
      }
      _armAudioLivenessWatch();
      return;
    }
    Logger.debug('[NativeBleTransport] audio path silent after reconnect — GATT connected is not capturing');
  }
}
