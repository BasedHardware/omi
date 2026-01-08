import 'dart:async';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

/// Bluetooth adapter that wraps over a Bluetooth BLE package.
/// This adapter provides a unified interface and exposes all necessary types,
/// so no other files need to import flutter_blue_plus packages directly.
/// Main motivation is to avoid third party dependencies spread across the codebase.
class BluetoothAdapter {
  /// Check if Bluetooth is supported
  static Future<bool> get isSupported {
    return FlutterBluePlus.isSupported;
  }

  /// Check if currently scanning
  static bool get isScanningNow {
    return FlutterBluePlus.isScanningNow;
  }

  /// Stream of scan results
  static Stream<List<dynamic>> get scanResults {
    return FlutterBluePlus.scanResults;
  }

  /// Stream of adapter state
  static Stream<dynamic> get adapterState {
    return FlutterBluePlus.adapterState;
  }

  /// Start scanning for devices
  static Future<void> startScan({
    Duration? timeout,
    List<dynamic>? withServices,
  }) async {
    final services = withServices?.cast<Guid>() ?? <Guid>[];
    return FlutterBluePlus.startScan(
      timeout: timeout,
      withServices: services,
    );
  }

  /// Stop scanning
  static Future<void> stopScan() async {
    return FlutterBluePlus.stopScan();
  }

  /// Cancel subscription when scan completes
  static void cancelWhenScanComplete(StreamSubscription subscription) {
    FlutterBluePlus.cancelWhenScanComplete(subscription);
  }

  /// Create a Guid from string
  static dynamic createGuid(String uuid) {
    return Guid(uuid);
  }

  /// Get the FlutterBluePlus class for advanced operations
  static dynamic get flutterBluePlus {
    return FlutterBluePlus;
  }
}

/// Platform-aware enum mappings
class BluetoothAdapterStateHelper {
  static dynamic get on {
    return BluetoothAdapterState.on;
  }

  static dynamic get off {
    return BluetoothAdapterState.off;
  }

  static dynamic get unknown {
    return BluetoothAdapterState.unknown;
  }
}

/// Platform-aware connection state mappings
class BluetoothConnectionStateHelper {
  static dynamic get connected {
    return BluetoothConnectionState.connected;
  }

  static dynamic get disconnected {
    return BluetoothConnectionState.disconnected;
  }
}
