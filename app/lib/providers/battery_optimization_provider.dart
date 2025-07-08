import 'package:flutter/foundation.dart';
import 'package:omi/services/battery_optimization.dart';
import 'package:omi/services/devices.dart';

enum BatteryOptimizationLevel {
  none,
  moderate,
  aggressive,
}

class BatteryOptimizationProvider extends ChangeNotifier {
  BatteryOptimizationService _batteryService = BatteryOptimizationService();
  bool _isOptimizedMode = false;
  BatteryOptimizationLevel _optimizationLevel = BatteryOptimizationLevel.moderate;
  bool _isMonitoringEnabled = true;
  Map<String, dynamic> _optimizationStats = {};

  // Getters
  bool get isOptimizedMode => _isOptimizedMode;
  BatteryOptimizationLevel get optimizationLevel => _optimizationLevel;
  bool get isMonitoringEnabled => _isMonitoringEnabled;
  Map<String, dynamic> get optimizationStats => _optimizationStats;

  /// Initialize battery optimization
  Future<void> initialize() async {
    debugPrint('BatteryOptimizationProvider: Initializing...');
    
    await _batteryService.initialize();
    
    // Enable moderate optimization by default
    enableModerateOptimization();
    
    // Start monitoring
    _startMonitoring();
    
    debugPrint('BatteryOptimizationProvider: Initialized');
  }

  /// Enable moderate battery optimization
  void enableModerateOptimization() {
    _optimizationLevel = BatteryOptimizationLevel.moderate;
    _isOptimizedMode = true;
    
    _batteryService.enableOptimizedMode();
    ServiceManager.instance().device.enableBatteryOptimization();
    
    debugPrint('BatteryOptimizationProvider: Moderate optimization enabled');
    notifyListeners();
  }

  /// Enable aggressive battery optimization
  void enableAggressiveOptimization() {
    _optimizationLevel = BatteryOptimizationLevel.aggressive;
    _isOptimizedMode = true;
    
    _batteryService.enableOptimizedMode();
    ServiceManager.instance().device.enableBatteryOptimization();
    
    debugPrint('BatteryOptimizationProvider: Aggressive optimization enabled');
    notifyListeners();
  }

  /// Disable battery optimization
  void disableOptimization() {
    _optimizationLevel = BatteryOptimizationLevel.none;
    _isOptimizedMode = false;
    
    _batteryService.disableOptimizedMode();
    ServiceManager.instance().device.disableBatteryOptimization();
    
    debugPrint('BatteryOptimizationProvider: Optimization disabled');
    notifyListeners();
  }

  /// Toggle monitoring on/off
  void toggleMonitoring() {
    _isMonitoringEnabled = !_isMonitoringEnabled;
    
    if (_isMonitoringEnabled) {
      _startMonitoring();
    } else {
      _stopMonitoring();
    }
    
    debugPrint('BatteryOptimizationProvider: Monitoring ${_isMonitoringEnabled ? "enabled" : "disabled"}');
    notifyListeners();
  }

  /// Start monitoring battery usage
  void _startMonitoring() {
    if (!_isMonitoringEnabled) return;
    
    // Update stats every 30 seconds
    Future.delayed(const Duration(seconds: 30), () {
      if (_isMonitoringEnabled) {
        _updateOptimizationStats();
        _startMonitoring(); // Continue monitoring
      }
    });
  }

  /// Stop monitoring
  void _stopMonitoring() {
    // Monitoring will stop automatically when _isMonitoringEnabled is false
  }

  /// Update optimization statistics
  void _updateOptimizationStats() {
    _optimizationStats = _batteryService.getOptimizationStats();
    notifyListeners();
  }

  /// Get battery drain rate
  double getBatteryDrainRate() {
    return _optimizationStats['batteryDrainRate'] ?? 0.0;
  }

  /// Get current battery level
  int getCurrentBatteryLevel() {
    return _optimizationStats['lastBatteryLevel'] ?? -1;
  }

  /// Get optimization recommendations
  List<String> getOptimizationRecommendations() {
    List<String> recommendations = [];
    
    double drainRate = getBatteryDrainRate();
    int batteryLevel = getCurrentBatteryLevel();
    
    if (drainRate > 15) {
      recommendations.add('High battery drain detected (${drainRate.toStringAsFixed(1)}%/hour). Consider enabling aggressive optimization.');
    }
    
    if (batteryLevel < 20) {
      recommendations.add('Low battery level ($batteryLevel%). Enabling aggressive optimization to extend battery life.');
    }
    
    if (drainRate < 5 && batteryLevel > 50) {
      recommendations.add('Battery usage is optimal. You can disable optimization for better performance.');
    }
    
    if (recommendations.isEmpty) {
      recommendations.add('Battery usage is within normal range.');
    }
    
    return recommendations;
  }

  /// Get optimization status summary
  String getOptimizationStatusSummary() {
    if (!_isOptimizedMode) {
      return 'Battery optimization is disabled';
    }
    
    switch (_optimizationLevel) {
      case BatteryOptimizationLevel.moderate:
        return 'Moderate battery optimization is active';
      case BatteryOptimizationLevel.aggressive:
        return 'Aggressive battery optimization is active';
      case BatteryOptimizationLevel.none:
        return 'No optimization active';
    }
  }

  /// Get battery usage statistics
  Map<String, dynamic> getBatteryUsageStats() {
    return {
      'isOptimized': _isOptimizedMode,
      'optimizationLevel': _optimizationLevel.toString(),
      'drainRate': getBatteryDrainRate(),
      'batteryLevel': getCurrentBatteryLevel(),
      'isMonitoring': _isMonitoringEnabled,
      'recommendations': getOptimizationRecommendations(),
      'statusSummary': getOptimizationStatusSummary(),
    };
  }

  /// Handle device connection state changes
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    _batteryService.onDeviceConnectionStateChanged(deviceId, state);
    _updateOptimizationStats();
  }

  /// Dispose of resources
  @override
  void dispose() {
    _batteryService.dispose();
    super.dispose();
  }
} 