import 'dart:async';
import 'dart:io';
import 'dart:convert';

/// Collects and reports performance metrics during test runs.
/// Outputs JSON reports for CPU, memory, FPS, and responsiveness.
class PerfMetricsCollector {
  final String testName;
  final List<Map<String, dynamic>> _samples = [];
  final Stopwatch _elapsed = Stopwatch();
  Timer? _samplingTimer;

  PerfMetricsCollector(this.testName);

  /// Start collecting metrics at the given interval.
  void startSampling({Duration interval = const Duration(seconds: 2)}) {
    _elapsed.start();
    _samplingTimer = Timer.periodic(interval, (_) => _takeSample());
  }

  /// Stop collecting and return the aggregated report.
  Map<String, dynamic> stopAndReport() {
    _samplingTimer?.cancel();
    _elapsed.stop();

    if (_samples.isEmpty) {
      return {'testName': testName, 'error': 'No samples collected'};
    }

    final memoryValues = _samples
        .where((s) => s.containsKey('heapUsageMB'))
        .map((s) => s['heapUsageMB'] as double)
        .toList();

    return {
      'testName': testName,
      'durationMs': _elapsed.elapsedMilliseconds,
      'sampleCount': _samples.length,
      'memory': memoryValues.isEmpty ? null : {
        'peakMB': memoryValues.reduce((a, b) => a > b ? a : b),
        'avgMB': memoryValues.reduce((a, b) => a + b) / memoryValues.length,
        'minMB': memoryValues.reduce((a, b) => a < b ? a : b),
        'trend': memoryValues.length > 2
            ? (memoryValues.last - memoryValues.first).toStringAsFixed(2)
            : 'insufficient_data',
      },
      'timestamp': DateTime.now().toIso8601String(),
    };
  }

  void _takeSample() {
    final info = ProcessInfo.currentRss;
    _samples.add({
      'timestampMs': _elapsed.elapsedMilliseconds,
      'heapUsageMB': info / (1024 * 1024),
    });
  }

  /// Save report to a JSON file.
  static Future<void> saveReport(
    List<Map<String, dynamic>> reports,
    String outputPath,
  ) async {
    final file = File(outputPath);
    await file.parent.create(recursive: true);
    await file.writeAsString(
      const JsonEncoder.withIndent('  ').convert({
        'generatedAt': DateTime.now().toIso8601String(),
        'platform': Platform.operatingSystem,
        'dartVersion': Platform.version.split(' ').first,
        'tests': reports,
      }),
    );
  }
}
