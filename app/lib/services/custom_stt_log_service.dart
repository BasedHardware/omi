import 'package:flutter/material.dart';

import 'package:omi/utils/logger.dart';

enum CustomSttLogLevel { info, warning, error }

class CustomSttLogEntry {
  final DateTime timestamp;
  final CustomSttLogLevel level;
  final String source;
  final String message;

  CustomSttLogEntry({
    required this.timestamp,
    required this.level,
    required this.source,
    required this.message,
  });

  String get formattedTime {
    final h = timestamp.hour.toString().padLeft(2, '0');
    final m = timestamp.minute.toString().padLeft(2, '0');
    final s = timestamp.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  String get formatted => '$formattedTime [$source] $message';
}

class CustomSttLogService {
  static final CustomSttLogService _instance = CustomSttLogService._();
  static CustomSttLogService get instance => _instance;

  CustomSttLogService._();

  final List<CustomSttLogEntry> _logs = [];
  static const int _maxLogs = 50;

  List<CustomSttLogEntry> get logs => List.unmodifiable(_logs.reversed.toList());

  bool get hasLogs => _logs.isNotEmpty;

  String get logsAsText => logs.map((l) {
        final prefix = l.level == CustomSttLogLevel.error
            ? '[ERROR] '
            : l.level == CustomSttLogLevel.warning
                ? '[WARN] '
                : '';
        return '$prefix${l.formatted}';
      }).join('\n');

  void log(CustomSttLogLevel level, String source, String message) {
    Logger.debug("[$source] $message");
    _logs.add(CustomSttLogEntry(
      timestamp: DateTime.now(),
      level: level,
      source: source,
      message: message,
    ));

    if (_logs.length > _maxLogs) {
      _logs.removeRange(0, _logs.length - _maxLogs);
    }
  }

  void info(String source, String message) => log(CustomSttLogLevel.info, source, message);
  void warning(String source, String message) => log(CustomSttLogLevel.warning, source, message);
  void error(String source, String message) => log(CustomSttLogLevel.error, source, message);

  void clear() => _logs.clear();
}
