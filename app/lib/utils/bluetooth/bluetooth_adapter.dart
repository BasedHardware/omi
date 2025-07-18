import 'dart:async';
import 'dart:io';

// Conditional imports for different platforms
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as standard_ble;
import 'package:flutter_blue_plus_windows/flutter_blue_plus_windows.dart' as windows_ble;

/// Bluetooth adapter that automatically chooses the right Bluetooth package
/// Uses flutter_blue_plus_windows on Windows, flutter_blue_plus on other platforms
///
/// This adapter provides a unified interface and exposes all necessary types,
/// so no other files need to import flutter_blue_plus packages directly.
class BluetoothAdapter {
  /// Check if Bluetooth is supported
  static Future<bool> get isSupported {
    if (Platform.isWindows) {
      return windows_ble.FlutterBluePlus.isSupported;
    } else {
      return standard_ble.FlutterBluePlus.isSupported;
    }
  }

  /// Check if currently scanning
  static bool get isScanningNow {
    if (Platform.isWindows) {
      return windows_ble.FlutterBluePlus.isScanningNow;
    } else {
      return standard_ble.FlutterBluePlus.isScanningNow;
    }
  }

  /// Stream of scan results
  static Stream<List<dynamic>> get scanResults {
    if (Platform.isWindows) {
      return windows_ble.FlutterBluePlus.scanResults;
    } else {
      return standard_ble.FlutterBluePlus.scanResults;
    }
  }

  /// Stream of adapter state
  static Stream<dynamic> get adapterState {
    if (Platform.isWindows) {
      return windows_ble.FlutterBluePlus.adapterState;
    } else {
      return standard_ble.FlutterBluePlus.adapterState;
    }
  }

  /// Start scanning for devices
  static Future<void> startScan({
    Duration? timeout,
    List<dynamic>? withServices,
  }) async {
    if (Platform.isWindows) {
      final services = withServices?.cast<windows_ble.Guid>() ?? <windows_ble.Guid>[];
      return windows_ble.FlutterBluePlus.startScan(
        timeout: timeout,
        withServices: services,
      );
    } else {
      final services = withServices?.cast<standard_ble.Guid>() ?? <standard_ble.Guid>[];
      return standard_ble.FlutterBluePlus.startScan(
        timeout: timeout,
        withServices: services,
      );
    }
  }

  /// Stop scanning
  static Future<void> stopScan() async {
    if (Platform.isWindows) {
      return windows_ble.FlutterBluePlus.stopScan();
    } else {
      return standard_ble.FlutterBluePlus.stopScan();
    }
  }

  /// Cancel subscription when scan completes
  static void cancelWhenScanComplete(StreamSubscription subscription) {
    if (Platform.isWindows) {
      windows_ble.FlutterBluePlus.cancelWhenScanComplete(subscription);
    } else {
      standard_ble.FlutterBluePlus.cancelWhenScanComplete(subscription);
    }
  }

  /// Create a Guid from string
  static dynamic createGuid(String uuid) {
    if (Platform.isWindows) {
      return windows_ble.Guid(uuid);
    } else {
      return standard_ble.Guid(uuid);
    }
  }

  /// Get the FlutterBluePlus class for advanced operations
  static dynamic get flutterBluePlus {
    if (Platform.isWindows) {
      return windows_ble.FlutterBluePlus;
    } else {
      return standard_ble.FlutterBluePlus;
    }
  }
}

/// Platform-aware enum mappings
class BluetoothAdapterStateHelper {
  static dynamic get on {
    if (Platform.isWindows) {
      return windows_ble.BluetoothAdapterState.on;
    } else {
      return standard_ble.BluetoothAdapterState.on;
    }
  }

  static dynamic get off {
    if (Platform.isWindows) {
      return windows_ble.BluetoothAdapterState.off;
    } else {
      return standard_ble.BluetoothAdapterState.off;
    }
  }

  static dynamic get unknown {
    if (Platform.isWindows) {
      return windows_ble.BluetoothAdapterState.unknown;
    } else {
      return standard_ble.BluetoothAdapterState.unknown;
    }
  }
}

/// Platform-aware connection state mappings
class BluetoothConnectionStateHelper {
  static dynamic get connected {
    if (Platform.isWindows) {
      return windows_ble.BluetoothConnectionState.connected;
    } else {
      return standard_ble.BluetoothConnectionState.connected;
    }
  }

  static dynamic get disconnected {
    if (Platform.isWindows) {
      return windows_ble.BluetoothConnectionState.disconnected;
    } else {
      return standard_ble.BluetoothConnectionState.disconnected;
    }
  }
}
