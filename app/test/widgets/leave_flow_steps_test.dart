import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/widgets/leave_flow_widgets.dart';
import 'package:omi/utils/other/temp.dart';

/// A three-step flow built the way DeleteAccount and CancelSubscriptionFlow are: each step is its
/// own route, and the last one can leave the whole flow.
class _Step extends StatefulWidget {
  const _Step({required this.index, required this.exit});

  final int index;
  final LeaveFlowExit exit;

  @override
  State<_Step> createState() => _StepState();
}

class _StepState extends State<_Step> {
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.index == 0) widget.exit.attach(context);
  }

  @override
  Widget build(BuildContext context) {
    return LeaveFlowStepScaffold(
      step: widget.index,
      stepCount: 3,
      title: 'Step title ${widget.index}',
      body: const SizedBox.shrink(),
      actions: widget.index < 2
          ? TextButton(
              onPressed: () => routeToPage(context, _Step(index: widget.index + 1, exit: widget.exit)),
              child: const Text('next'),
            )
          : TextButton(onPressed: () => widget.exit.close(context, true), child: const Text('leave')),
    );
  }
}

void main() {
  Future<(LeaveFlowExit, Future<Object?> Function())> pumpFlow(WidgetTester tester) async {
    final exit = LeaveFlowExit();
    late BuildContext homeContext;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('en')],
        home: Builder(builder: (context) {
          homeContext = context;
          return const Scaffold(body: Text('home'));
        }),
      ),
    );
    Future<Object?> open() => Navigator.of(homeContext).push<Object?>(
          MaterialPageRoute(builder: (_) => _Step(index: 0, exit: exit)),
        );
    return (exit, open);
  }

  testWidgets('back steps back one step at a time', (tester) async {
    final (_, open) = await pumpFlow(tester);
    open();
    await tester.pumpAndSettle();
    await tester.tap(find.text('next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('next'));
    await tester.pumpAndSettle();
    expect(find.text('Step title 2'), findsOneWidget);
    expect(find.bySemanticsLabel('Step 3 of 3'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Step title 1'), findsOneWidget);

    // System back behaves the same as the on-screen control.
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.text('Step title 0'), findsOneWidget);
  });

  testWidgets('close leaves every step and completes the flow with its result', (tester) async {
    final (exit, open) = await pumpFlow(tester);
    final result = open();
    await tester.pumpAndSettle();
    await tester.tap(find.text('next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('next'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('leave'));
    await tester.pumpAndSettle();
    expect(find.text('home'), findsOneWidget);
    expect(await result, isTrue);
    expect(exit.finished, isTrue);
  });

  testWidgets('a step that cannot pop blocks system back', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: [Locale('en')],
        home: Scaffold(body: Text('home')),
      ),
    );
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.push(MaterialPageRoute(
      builder: (_) => const LeaveFlowStepScaffold(
        step: 2,
        stepCount: 3,
        title: 'busy',
        canPop: false,
        body: SizedBox.shrink(),
        actions: SizedBox.shrink(),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.text('busy'), findsOneWidget);
  });
}
