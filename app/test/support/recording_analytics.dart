import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// In-memory [AnalyticsAdapter] plus event lookup helpers for tests that
/// assert on PostHog wire traffic without a real SDK.
class _RecordingAdapter implements AnalyticsAdapter {
  final events = <String>[];
  final properties = <Map<String, Object>>[];
  bool initialized = false;

  @override
  bool get isInitialized => initialized;

  @override
  Future<void> init() async => initialized = true;

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(eventName);
    this.properties.add(Map.of(properties ?? {}));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class RecordingAnalytics {
  final _RecordingAdapter _adapter = _RecordingAdapter();

  AnalyticsAdapter get adapter => _adapter;

  List<String> get names => _adapter.events;

  Iterable<Map<String, Object>> propertiesOf(String eventName) sync* {
    for (var i = 0; i < _adapter.events.length; i++) {
      if (_adapter.events[i] == eventName) yield _adapter.properties[i];
    }
  }

  /// Asserts exactly one [eventName] was recorded containing [props].
  void expectSingle(String eventName, Map<String, Object> props) {
    final recorded = propertiesOf(eventName).toList();
    expect(recorded, hasLength(1), reason: 'expected one $eventName, got ${_adapter.events}');
    for (final entry in props.entries) {
      expect(recorded.single, containsPair(entry.key, entry.value), reason: '$eventName properties');
    }
  }
}
