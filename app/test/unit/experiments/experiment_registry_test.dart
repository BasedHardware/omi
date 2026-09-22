import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/experiment_registry.dart';

void main() {
  test('operational spec matches shipping experiment contract', () {
    final spec =
        jsonDecode(File('docs/experiments/summary-feedback-layout.json').readAsStringSync()) as Map<String, dynamic>;
    final definition = MobileExperiments.summaryFeedbackLayout;
    expect(spec['key'], definition.key);
    expect(spec['version'], definition.version);
    expect((spec['variants'] as List).map((variant) => variant['key']).toSet(), definition.variants.keys.toSet());
    expect(spec['default_variant'], definition.defaultVariant);
    expect((spec['surfaces'] as List).toSet(), definition.surfaces);
    expect(DateTime.parse(spec['expires_at']), definition.expiresAt);
    expect((spec['targeting']['namespaces'] as List).every(definition.namespaces.contains), true);
    expect(spec['targeting']['minimum_build'], greaterThanOrEqualTo(definition.minimumBuild));
  });
}
