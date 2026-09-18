import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/startup_failure_app.dart';

void main() {
  group('StartupFailureApp', () {
    testWidgets('renders the actual error text instead of a blank screen', (tester) async {
      // The regression this guards: a StateError thrown by
      // validateApplicationStartupRouting() used to leave the launch storyboard
      // up forever, because runApp() was never reached and the zone handler only
      // called debugPrint — invisible in profile and release builds.
      final error = StateError(
        'Profile local_dev requires a loopback or private-network API endpoint; '
        'use mobile_beta for https://api.omiapi.com/.',
      );

      await tester.pumpWidget(StartupFailureApp(error: error, stack: StackTrace.current));

      expect(find.text('Omi could not start'), findsOneWidget);
      expect(
        find.textContaining('requires a loopback or private-network API endpoint', findRichText: true),
        findsOneWidget,
      );
    });

    testWidgets('renders without any provider, service or localisation scope', (tester) async {
      // It must survive being shown when startup itself failed, so it cannot
      // depend on anything _init() sets up. Pumping it bare is the assertion.
      await tester.pumpWidget(StartupFailureApp(error: Exception('boom'), stack: null));

      expect(tester.takeException(), isNull);
      expect(find.byType(MaterialApp), findsOneWidget);
    });

    testWidgets('error text is selectable so it can be copied off-device', (tester) async {
      // There is no debugger attached in the situation this screen exists for.
      await tester.pumpWidget(StartupFailureApp(error: Exception('copy me'), stack: null));

      expect(find.byType(SelectableText), findsOneWidget);
    });
  });
}
