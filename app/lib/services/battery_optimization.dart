import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';

/// Battery optimization service to reduce power consumption
class BatteryOptimizationService {
  static final BatteryOptimizationService _instance = BatteryOptimizationService._internal();
  factory BatteryOptimizationService() => _instance;
  BatteryOptimizationService._internal();

  // Battery optimization settings
  static const int _maxScanDuration = 30; // seconds
  static const int _scanInterval = 300; // 5 minutes between scans
  static const int _connectionTimeout = 10; // seconds
  static const int _maxReconnectionAttempts = 3;
  static const int _reconnectionDelay = 5000; // 5 seconds

  Timer? _scanTimer;
  Timer? _batteryCheckTimer;
  int _reconnectionAttempts = 0;
  DateTime? _lastScanTime;
  bool _isOptimizedMode = false;
  bool _isConnected = false;

  // Battery level tracking
  int _lastBatteryLevel = -1;
  DateTime? _lastBatteryCheck;
  List<int> _batteryHistory = [];

  /// Initialize battery optimization
  Future<void> initialize() async {
    debugPrint('BatteryOptimizationService: Initializing...');
    
    // Start battery monitoring
    _startBatteryMonitoring();
    
    // Set up scan optimization
    _setupScanOptimization();
    
    debugPrint('BatteryOptimizationService: Initialized');
  }

  /// Enable optimized mode for better battery life
  void enableOptimizedMode() {
    _isOptimizedMode = true;
    debugPrint('BatteryOptimizationService: Optimized mode enabled');
    
    // Reduce scan frequency
    _reduceScanFrequency();
    
    // Optimize background services
    _optimizeBackgroundServices();
  }

  /// Disable optimized mode for better performance
  void disableOptimizedMode() {
    _isOptimizedMode = false;
    debugPrint('BatteryOptimizationService: Optimized mode disabled');
    
    // Restore normal scan frequency
    _restoreScanFrequency();
  }

  /// Start battery level monitoring
  void _startBatteryMonitoring() {
    _batteryCheckTimer = Timer.periodic(const Duration(minutes: 5), (timer) {
      _checkBatteryLevel();
    });
  }

  /// Check battery level and adjust optimization accordingly
  Future<void> _checkBatteryLevel() async {
    try {
      // Get current battery level (this would need platform-specific implementation)
      int currentBatteryLevel = await _getBatteryLevel();
      
      if (currentBatteryLevel != -1) {
        _batteryHistory.add(currentBatteryLevel);
        
        // Keep only last 10 readings
        if (_batteryHistory.length > 10) {
          _batteryHistory.removeAt(0);
        }
        
        // Calculate battery drain rate
        double drainRate = _calculateBatteryDrainRate();
        
        debugPrint('BatteryOptimizationService: Battery level: $currentBatteryLevel%, Drain rate: ${drainRate.toStringAsFixed(2)}%/hour');
        
        // Enable aggressive optimization if battery is low or draining fast
        if (currentBatteryLevel < 20 || drainRate > 15) {
          _enableAggressiveOptimization();
        } else if (currentBatteryLevel > 50 && drainRate < 5) {
          _disableAggressiveOptimization();
        }
        
        _lastBatteryLevel = currentBatteryLevel;
        _lastBatteryCheck = DateTime.now();
      }
    } catch (e) {
      debugPrint('BatteryOptimizationService: Error checking battery level: $e');
    }
  }

  /// Calculate battery drain rate (%/hour)
  double _calculateBatteryDrainRate() {
    if (_batteryHistory.length < 2) return 0.0;
    
    int oldestLevel = _batteryHistory.first;
    int newestLevel = _batteryHistory.last;
    int timeDiff = _batteryHistory.length * 5; // 5 minutes per reading
    
    if (timeDiff == 0) return 0.0;
    
    double drainPerMinute = (oldestLevel - newestLevel) / timeDiff;
    return drainPerMinute * 60; // Convert to per hour
  }

  /// Get battery level (platform-specific implementation needed)
  Future<int> _getBatteryLevel() async {
    // This would need to be implemented with platform-specific code
    // For now, return -1 to indicate not available
    return -1;
  }

  /// Set up optimized Bluetooth scanning
  void _setupScanOptimization() {
    // Stop any existing scan timer
    _scanTimer?.cancel();
    
    // Create optimized scan timer
    _scanTimer = Timer.periodic(Duration(seconds: _scanInterval), (timer) {
      if (!_isConnected && _shouldScan()) {
        _performOptimizedScan();
      }
    });
  }

  /// Check if scanning should be performed
  bool _shouldScan() {
    if (_lastScanTime == null) return true;
    
    int secondsSinceLastScan = DateTime.now().difference(_lastScanTime!).inSeconds;
    return secondsSinceLastScan >= _scanInterval;
  }

  /// Perform optimized Bluetooth scan
  Future<void> _performOptimizedScan() async {
    if (_isOptimizedMode) {
      debugPrint('BatteryOptimizationService: Performing optimized scan');
      
      try {
        // Use shorter scan duration in optimized mode
        await ServiceManager.instance().device.discover(timeout: _maxScanDuration ~/ 2);
        _lastScanTime = DateTime.now();
      } catch (e) {
        debugPrint('BatteryOptimizationService: Scan error: $e');
      }
    }
  }

  /// Reduce scan frequency for better battery life
  void _reduceScanFrequency() {
    debugPrint('BatteryOptimizationService: Reducing scan frequency');
    
    // Stop current scanning if active
    if (ServiceManager.instance().device.status == DeviceServiceStatus.scanning) {
      // Note: This would need to be implemented in the device service
    }
    
    // Increase scan interval
    _scanTimer?.cancel();
    _scanTimer = Timer.periodic(Duration(seconds: _scanInterval * 2), (timer) {
      if (!_isConnected && _shouldScan()) {
        _performOptimizedScan();
      }
    });
  }

  /// Restore normal scan frequency
  void _restoreScanFrequency() {
    debugPrint('BatteryOptimizationService: Restoring normal scan frequency');
    
    _scanTimer?.cancel();
    _scanTimer = Timer.periodic(Duration(seconds: _scanInterval), (timer) {
      if (!_isConnected && _shouldScan()) {
        _performOptimizedScan();
      }
    });
  }

  /// Optimize background services
  void _optimizeBackgroundServices() {
    debugPrint('BatteryOptimizationService: Optimizing background services');
    
    // Reduce background service update frequency
    // This would need to be implemented in the background service
  }

  /// Enable aggressive battery optimization
  void _enableAggressiveOptimization() {
    debugPrint('BatteryOptimizationService: Enabling aggressive optimization');
    
    // Stop all non-essential background activities
    _stopNonEssentialServices();
    
    // Reduce scan frequency even more
    _scanTimer?.cancel();
    _scanTimer = Timer.periodic(Duration(seconds: _scanInterval * 4), (timer) {
      if (!_isConnected && _shouldScan()) {
        _performOptimizedScan();
      }
    });
  }

  /// Disable aggressive battery optimization
  void _disableAggressiveOptimization() {
    debugPrint('BatteryOptimizationService: Disabling aggressive optimization');
    
    // Restore normal service levels
    _restoreNormalServices();
    
    // Restore normal scan frequency
    _restoreScanFrequency();
  }

  /// Stop non-essential background services
  void _stopNonEssentialServices() {
    // Stop continuous Bluetooth scanning
    if (ServiceManager.instance().device.status == DeviceServiceStatus.scanning) {
      // Note: This would need to be implemented in the device service
    }
    
    // Reduce background service frequency
    // This would need to be implemented in the background service
  }

  /// Restore normal service levels
  void _restoreNormalServices() {
    // Restore normal background service frequency
    // This would need to be implemented in the background service
  }

  /// Handle device connection state changes
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    _isConnected = state == DeviceConnectionState.connected;
    
    if (state == DeviceConnectionState.connected) {
      _reconnectionAttempts = 0;
      debugPrint('BatteryOptimizationService: Device connected, resetting reconnection attempts');
    } else if (state == DeviceConnectionState.disconnected) {
      _handleDisconnection();
    }
  }

  /// Handle device disconnection with optimization
  void _handleDisconnection() {
    debugPrint('BatteryOptimizationService: Device disconnected');
    
    if (_reconnectionAttempts < _maxReconnectionAttempts) {
      _reconnectionAttempts++;
      debugPrint('BatteryOptimizationService: Attempting reconnection ${_reconnectionAttempts}/$_maxReconnectionAttempts');
      
      // Delay reconnection to avoid rapid reconnection attempts
      Timer(Duration(milliseconds: _reconnectionDelay), () {
        _attemptReconnection();
      });
    } else {
      debugPrint('BatteryOptimizationService: Max reconnection attempts reached, stopping');
      _stopReconnectionAttempts();
    }
  }

  /// Attempt to reconnect to device
  Future<void> _attemptReconnection() async {
    try {
      // This would need to be implemented based on the current device connection logic
      debugPrint('BatteryOptimizationService: Attempting reconnection...');
    } catch (e) {
      debugPrint('BatteryOptimizationService: Reconnection failed: $e');
    }
  }

  /// Stop reconnection attempts to save battery
  void _stopReconnectionAttempts() {
    debugPrint('BatteryOptimizationService: Stopping reconnection attempts to save battery');
    
    // Stop scanning for devices
    if (ServiceManager.instance().device.status == DeviceServiceStatus.scanning) {
      // Note: This would need to be implemented in the device service
    }
  }

  /// Get battery optimization statistics
  Map<String, dynamic> getOptimizationStats() {
    return {
      'isOptimizedMode': _isOptimizedMode,
      'isConnected': _isConnected,
      'reconnectionAttempts': _reconnectionAttempts,
      'lastScanTime': _lastScanTime?.toIso8601String(),
      'lastBatteryLevel': _lastBatteryLevel,
      'lastBatteryCheck': _lastBatteryCheck?.toIso8601String(),
      'batteryDrainRate': _calculateBatteryDrainRate(),
      'batteryHistory': _batteryHistory,
    };
  }

  /// Dispose of resources
  void dispose() {
    _scanTimer?.cancel();
    _batteryCheckTimer?.cancel();
    debugPrint('BatteryOptimizationService: Disposed');
  }
} 