// Writes the selected scenarios' PNGs to OMI_AUDIT_OUTPUT. Run it through
// app/scripts/visual_audit.sh (see app/e2e/SKILL.md, "Visual audit"), not directly.
import 'dart:convert';
import 'dart:io';

import 'harness.dart';
import 'suite.dart';

void main() {
  final output = Platform.environment['OMI_AUDIT_OUTPUT'];
  if (output == null || output.isEmpty) throw StateError('Set OMI_AUDIT_OUTPUT to an empty directory outside Git');
  // Ids this suite does not have are pages with no equivalent at this revision; the script has
  // already rejected ids that no suite knows, and the gallery shows these as "did not exist".
  final only =
      (Platform.environment['OMI_AUDIT_ONLY'] ?? '').split(',').map((s) => s.trim()).where((s) => s.isNotEmpty);
  final selected =
      only.isEmpty ? auditSuite.scenarios : auditSuite.scenarios.where((s) => only.contains(s.id)).toList();
  final dir = Directory(output)..createSync(recursive: true);
  // What this revision was asked for, so the gallery can tell "failed" from "did not exist".
  File('${dir.path}/scenarios.json').writeAsStringSync(const JsonEncoder.withIndent('  ').convert({
    'suite': auditSuite.name,
    'scenarios': [
      for (final s in selected) {'id': s.id, 'title': s.title, 'page': s.page, 'state': s.state},
    ],
  }));
  runAuditScenarios(auditSuite, only: selected, output: dir);
}
