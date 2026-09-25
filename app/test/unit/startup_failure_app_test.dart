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

      expect(find.text('Omi couldn’t start'), findsOneWidget);
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

    testWidgets('no stack trace prints only the error, never a literal "null"', (tester) async {
      await tester.pumpWidget(StartupFailureApp(error: Exception('no stack'), stack: null));

      final text = tester.widget<SelectableText>(find.byType(SelectableText)).data!;
      expect(text, 'Exception: no stack');
    });

    testWidgets('a runtime failure offers Try Again, which re-runs start-up, and Contact Support', (tester) async {
      var retries = 0;
      await tester.pumpWidget(
        StartupFailureApp(
          error: Exception('socket closed'),
          onRetry: () async => retries++,
        ),
      );

      expect(find.textContaining('Check your connection'), findsOneWidget);
      expect(find.byKey(const Key('startup_failure_contact_support')), findsOneWidget);

      await tester.tap(find.byKey(const Key('startup_failure_try_again')));
      await tester.pump();
      expect(retries, 1);
    });

    testWidgets('a rejected configuration blames the build and offers support, not Try Again', (tester) async {
      await tester.pumpWidget(
        StartupFailureApp(
          error: StartupConfigurationError(StateError('Profile local_dev requires a loopback endpoint')),
          onRetry: () async {},
        ),
      );

      expect(find.textContaining('configuration problem'), findsOneWidget);
      expect(find.textContaining('requires a loopback endpoint', findRichText: true), findsOneWidget);
      expect(find.byKey(const Key('startup_failure_try_again')), findsNothing);
      expect(find.byKey(const Key('startup_failure_contact_support')), findsOneWidget);
    });
  });
}
