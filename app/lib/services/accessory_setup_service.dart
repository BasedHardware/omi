import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class AccessorySetupService {
  static const MethodChannel _channel = MethodChannel('com.omi.ios/accessorySetup');
  static AccessorySetupService? _instance;

  // Event stream for accessory events
  static Stream<AccessoryEvent>? _eventStream;

  AccessorySetupService._();

  static AccessorySetupService get instance {
    _instance ??= AccessorySetupService._();
    return _instance!;
  }

  /// Initialize the service and set up event handlers
  void initialize() {
    if (Platform.isIOS) {
      _channel.setMethodCallHandler(_handleMethodCall);
    }
  }

  /// Check if AccessorySetupKit is available (iOS 18+)
  Future<bool> isAccessorySetupKitAvailable() async {
    if (!Platform.isIOS) return false;

    try {
      final result = await _channel.invokeMethod<bool>('isAccessorySetupKitAvailable');
      return result ?? false;
    } catch (e) {
      debugPrint('Error checking AccessorySetupKit availability: $e');
      return false;
    }
  }

  /// Show the native accessory picker
  Future<bool> showAccessoryPicker() async {
    if (!Platform.isIOS) {
      throw UnsupportedError('AccessorySetupKit is only available on iOS');
    }

    try {
      final result = await _channel.invokeMethod<bool>('showAccessoryPicker');
      return result ?? false;
    } catch (e) {
      debugPrint('Error showing accessory picker: $e');
      rethrow;
    }
  }

  /// Get list of connected accessories
  Future<List<ConnectedAccessory>> getConnectedAccessories() async {
    if (!Platform.isIOS) return [];

    try {
      final result = await _channel.invokeMethod<List>('getConnectedAccessories');
      if (result == null) return [];

      return result.cast<Map<dynamic, dynamic>>().map((accessory) => ConnectedAccessory.fromMap(accessory)).toList();
    } catch (e) {
      debugPrint('Error getting connected accessories: $e');
      return [];
    }
  }

  /// Remove an accessory
  Future<bool> removeAccessory(String accessoryId) async {
    if (!Platform.isIOS) return false;

    try {
      final result = await _channel.invokeMethod<bool>('removeAccessory', {
        'accessoryId': accessoryId,
      });
      return result ?? false;
    } catch (e) {
      debugPrint('Error removing accessory: $e');
      return false;
    }
  }

  /// Handle method calls from native side
  Future<dynamic> _handleMethodCall(MethodCall call) async {
    switch (call.method) {
      case 'onAccessoryEvent':
        final arguments = call.arguments as Map<dynamic, dynamic>;
        final eventType = arguments['eventType'] as String;
        final eventData = arguments['data'] as Map<dynamic, dynamic>;

        final event = AccessoryEvent(
          type: eventType,
          data: eventData.cast<String, dynamic>(),
        );

        _eventController.add(event);
        break;

      default:
        debugPrint('Unhandled method call: ${call.method}');
    }
  }

  /// Stream of accessory events
  static Stream<AccessoryEvent> get eventStream {
    _eventStream ??= _eventController.stream.asBroadcastStream();
    return _eventStream!;
  }

  static final _eventController = StreamController<AccessoryEvent>.broadcast();

  /// Dispose resources
  void dispose() {
    _eventController.close();
  }
}

/// Represents a connected accessory
class ConnectedAccessory {
  final String accessoryId;
  final String displayName;
  final String bluetoothIdentifier;

  ConnectedAccessory({
    required this.accessoryId,
    required this.displayName,
    required this.bluetoothIdentifier,
  });

  factory ConnectedAccessory.fromMap(Map<dynamic, dynamic> map) {
    return ConnectedAccessory(
      accessoryId: map['accessoryId'] as String,
      displayName: map['displayName'] as String,
      bluetoothIdentifier: map['bluetoothIdentifier'] as String,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'accessoryId': accessoryId,
      'displayName': displayName,
      'bluetoothIdentifier': bluetoothIdentifier,
    };
  }

  @override
  String toString() {
    return 'ConnectedAccessory(accessoryId: $accessoryId, displayName: $displayName, bluetoothIdentifier: $bluetoothIdentifier)';
  }
}

/// Represents an accessory event
class AccessoryEvent {
  final String type;
  final Map<String, dynamic> data;

  AccessoryEvent({
    required this.type,
    required this.data,
  });

  @override
  String toString() {
    return 'AccessoryEvent(type: $type, data: $data)';
  }
}

/// Event types from AccessorySetupKit
class AccessoryEventTypes {
  static const String sessionActivated = 'sessionActivated';
  static const String accessoryAdded = 'accessoryAdded';
  static const String accessoryChanged = 'accessoryChanged';
  static const String accessoryRemoved = 'accessoryRemoved';
  static const String pickerDidPresent = 'pickerDidPresent';
  static const String pickerDidDismiss = 'pickerDidDismiss';
}
