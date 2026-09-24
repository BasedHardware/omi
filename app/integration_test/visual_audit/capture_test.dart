// Writes the registered scenarios' PNGs to OMI_AUDIT_OUTPUT. Run it through
// app/scripts/visual_audit.sh (see app/e2e/SKILL.md, "Visual audit"), not directly.
import 'dart:convert';
import 'dart:io';

import 'harness.dart';
import 'registry.dart';

void main() {
  final output = Platform.environment['OMI_AUDIT_OUTPUT'];
  if (output == null || output.isEmpty) throw StateError('Set OMI_AUDIT_OUTPUT to an empty directory outside Git');
  final only =
      (Platform.environment['OMI_AUDIT_ONLY'] ?? '').split(',').map((s) => s.trim()).where((s) => s.isNotEmpty);
  final unknown = only.where((id) => !auditScenarios.any((s) => s.id == id)).toList();
  if (unknown.isNotEmpty) throw ArgumentError('Unknown scenario ids: ${unknown.join(', ')}');
  final selected = only.isEmpty ? auditScenarios : auditScenarios.where((s) => only.contains(s.id)).toList();
  final dir = Directory(output)..createSync(recursive: true);
  // What was asked for, so the gallery can show a scenario that failed on one side.
  File('${dir.path}/scenarios.json').writeAsStringSync(const JsonEncoder.withIndent('  ').convert([
    for (final s in selected) {'id': s.id, 'title': s.title, 'page': s.page, 'state': s.state},
  ]));
  runAuditScenarios(selected, output: dir);
}
