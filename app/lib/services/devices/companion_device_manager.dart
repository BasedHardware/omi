import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

// Dart interface for Android's CompanionDeviceManager
// Note: This only works on Android
class CompanionDeviceManagerService {
  static const MethodChannel _methodChannel = MethodChannel('com.omi.companion_device');
  static const EventChannel _eventChannel = EventChannel('com.omi.companion_device/events');

  static CompanionDeviceManagerService? _instance;

  final StreamController<CompanionDeviceEvent> _eventController = StreamController<CompanionDeviceEvent>.broadcast();

  StreamSubscription? _eventSubscription;

  CompanionDeviceManagerService._() {
    _setupEventListener();
  }

  /// Get singleton instance
  static CompanionDeviceManagerService get instance {
    _instance ??= CompanionDeviceManagerService._();
    return _instance!;
  }

  /// Stream of device presence events
  Stream<CompanionDeviceEvent> get events => _eventController.stream;

  void _setupEventListener() {
    _eventSubscription = _eventChannel.receiveBroadcastStream().listen(
      (dynamic event) {
        if (event is Map) {
          final type = event['type'] as String?;
          final deviceAddress = event['deviceAddress'] as String?;

          switch (type) {
            case 'deviceAppeared':
              if (deviceAddress != null) {
                _eventController.add(CompanionDeviceEvent.appeared(deviceAddress));
              }
              break;
            case 'deviceDisappeared':
              if (deviceAddress != null) {
                _eventController.add(CompanionDeviceEvent.disappeared(deviceAddress));
              }
              break;
            case 'associationCreated':
              if (deviceAddress != null) {
                _eventController.add(CompanionDeviceEvent.associated(deviceAddress));
              }
              break;
            case 'associationPending':
              // Association dialog is being shown
              break;
          }
        }
      },
      onError: (error) {
        debugPrint('CompanionDeviceManager event error: $error');
      },
    );
  }

  /// Check if CompanionDeviceManager is supported on this device.
  /// Returns true on Android 8+ (API 26+).
  Future<bool> isSupported() async {
    if (!Platform.isAndroid) return false;

    try {
      final result = await _methodChannel.invokeMethod<bool>('isSupported');
      return result ?? false;
    } on PlatformException catch (e) {
      debugPrint('CompanionDeviceManager isSupported error: ${e.message}');
      return false;
    }
  }

  /// Check if device presence observing is supported.
  /// Returns true on Android 13+ (API 33+).
  Future<bool> isPresenceObservingSupported() async {
    if (!Platform.isAndroid) return false;

    try {
      final result = await _methodChannel.invokeMethod<bool>('isPresenceObservingSupported');
      return result ?? false;
    } on PlatformException catch (e) {
      debugPrint('CompanionDeviceManager isPresenceObservingSupported error: ${e.message}');
      return false;
    }
  }

  /// Get list of associated device MAC addresses.
  Future<List<String>> getAssociatedDevices() async {
    if (!Platform.isAndroid) return [];

    try {
      final result = await _methodChannel.invokeMethod<List<dynamic>>('getAssociatedDevices');
      return result?.cast<String>() ?? [];
    } on PlatformException catch (e) {
      debugPrint('CompanionDeviceManager getAssociatedDevices error: ${e.message}');
      return [];
    }
  }

  /// Check if a device is already associated.
  Future<bool> isDeviceAssociated(String deviceAddress) async {
    final associated = await getAssociatedDevices();
    final normalizedAddress = deviceAddress.toLowerCase();
    return associated.any((addr) => addr.toLowerCase() == normalizedAddress);
  }

  /// Associate with a BLE device.
  Future<AssociationResult> associate({
    String? deviceAddress,
    String? deviceName,
    String? serviceUuid,
  }) async {
    if (!Platform.isAndroid) {
      return AssociationResult(success: false, error: 'Only supported on Android');
    }

    try {
      final result = await _methodChannel.invokeMethod<Map<dynamic, dynamic>>('associate', {
        'deviceAddress': deviceAddress,
        'deviceName': deviceName,
        'serviceUuid': serviceUuid,
      });

      if (result == null) {
        return AssociationResult(success: false, error: 'No result returned');
      }

      if (result['pending'] == true) {
        return AssociationResult(success: true, pending: true);
      }

      if (result['associated'] == true) {
        return AssociationResult(
          success: true,
          deviceAddress: result['deviceAddress'] as String?,
        );
      }

      return AssociationResult(success: false, error: 'Unknown result');
    } on PlatformException catch (e) {
      debugPrint('CompanionDeviceManager associate error: ${e.message}');
      return AssociationResult(success: false, error: e.message);
    }
  }

  /// Remove association with a device.
  Future<bool> disassociate(String deviceAddress) async {
    if (!Platform.isAndroid) return false;

    try {
      final result = await _methodChannel.invokeMethod<bool>('disassociate', {
        'deviceAddress': deviceAddress,
      });
      return result ?? false;
    } on PlatformException catch (e) {
      debugPrint('CompanionDeviceManager disassociate error: ${e.message}');
      return false;
    }
  }

  /// Start observing device presence.
  ///
  /// Once started, the system will notify via [events] stream when the
  /// device appears or disappears. This works even when the app is killed.
  ///
  /// The device must be associated first using [associate].
  Future<bool> startObservingDevicePresence(String deviceAddress) async {
    if (!Platform.isAndroid) return false;

    try {
      final result = await _methodChannel.invokeMethod<bool>('startObservingDevicePresence', {
        'deviceAddress': deviceAddress,
      });
      return result ?? false;
    } on PlatformException catch (e) {
      debugPrint('CompanionDeviceManager startObservingDevicePresence error: ${e.message}');
      return false;
    }
  }

  /// Stop observing device presence.
  Future<bool> stopObservingDevicePresence(String deviceAddress) async {
    if (!Platform.isAndroid) return false;

    try {
      final result = await _methodChannel.invokeMethod<bool>('stopObservingDevicePresence', {
        'deviceAddress': deviceAddress,
      });
      return result ?? false;
    } on PlatformException catch (e) {
      debugPrint('CompanionDeviceManager stopObservingDevicePresence error: ${e.message}');
      return false;
    }
  }

  /// Dispose resources
  void dispose() {
    _eventSubscription?.cancel();
    _eventController.close();
  }
}

/// Event types for companion device presence changes
enum CompanionDeviceEventType {
  appeared,
  disappeared,
  associated,
}

/// Event representing a change in companion device state
class CompanionDeviceEvent {
  final CompanionDeviceEventType type;
  final String deviceAddress;

  CompanionDeviceEvent._(this.type, this.deviceAddress);

  factory CompanionDeviceEvent.appeared(String deviceAddress) {
    return CompanionDeviceEvent._(CompanionDeviceEventType.appeared, deviceAddress);
  }

  factory CompanionDeviceEvent.disappeared(String deviceAddress) {
    return CompanionDeviceEvent._(CompanionDeviceEventType.disappeared, deviceAddress);
  }

  factory CompanionDeviceEvent.associated(String deviceAddress) {
    return CompanionDeviceEvent._(CompanionDeviceEventType.associated, deviceAddress);
  }

  @override
  String toString() => 'CompanionDeviceEvent($type, $deviceAddress)';
}

/// Result of an association attempt
class AssociationResult {
  final bool success;
  final bool pending;
  final String? deviceAddress;
  final String? error;

  AssociationResult({
    required this.success,
    this.pending = false,
    this.deviceAddress,
    this.error,
  });

  @override
  String toString() => 'AssociationResult(success: $success, pending: $pending, '
      'deviceAddress: $deviceAddress, error: $error)';
}
