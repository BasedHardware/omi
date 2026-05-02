import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/widgets/jira_chip.dart';

class _RecordingLauncher {
  final List<Uri> calls = [];
  LaunchMode? lastMode;
  bool throwOnLaunch = false;

  Future<bool> launch(Uri uri, {LaunchMode mode = LaunchMode.platformDefault}) async {
    if (throwOnLaunch) throw Exception('Safari unavailable');
    calls.add(uri);
    lastMode = mode;
    return true;
  }
}

Widget _harness(Widget child) {
  return MaterialApp(
    home: Scaffold(body: Center(child: child)),
  );
}

const _fakeSource = ExternalSource(
  source: 'jira',
  externalId: 'PROJ-123',
  url: 'https://x.atlassian.net/browse/PROJ-123',
);

void main() {
  testWidgets('renders external_id text', (tester) async {
    await tester.pumpWidget(_harness(JiraChip(source: _fakeSource, launchUrl: _RecordingLauncher().launch)));

    expect(find.text('PROJ-123'), findsOneWidget);
  });

  testWidgets('forSource returns SizedBox.shrink for null', (tester) async {
    await tester.pumpWidget(_harness(JiraChip.forSource(null)));

    expect(find.byType(JiraChip), findsNothing);
    expect(find.text('PROJ-123'), findsNothing);
  });

  testWidgets('forSource returns chip for non-null source', (tester) async {
    await tester.pumpWidget(_harness(JiraChip.forSource(_fakeSource)));

    expect(find.byType(JiraChip), findsOneWidget);
    expect(find.text('PROJ-123'), findsOneWidget);
  });

  testWidgets('tap launches the source url externally', (tester) async {
    final launcher = _RecordingLauncher();
    await tester.pumpWidget(_harness(JiraChip(source: _fakeSource, launchUrl: launcher.launch)));

    await tester.tap(find.byType(JiraChip));
    await tester.pumpAndSettle();

    expect(launcher.calls, hasLength(1));
    expect(launcher.calls.single.toString(), _fakeSource.url);
    expect(launcher.lastMode, LaunchMode.externalApplication);
  });

  testWidgets('tap swallows launcher errors without throwing', (tester) async {
    final launcher = _RecordingLauncher()..throwOnLaunch = true;
    await tester.pumpWidget(_harness(JiraChip(source: _fakeSource, launchUrl: launcher.launch)));

    // Should NOT throw or surface to the test failure path.
    await tester.tap(find.byType(JiraChip));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
